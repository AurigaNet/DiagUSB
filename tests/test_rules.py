# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Pruebas unitarias para el motor de reglas de DiagUSB."""

import sys
from pathlib import Path
from datetime import datetime, timedelta, timezone

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from diagusb.core.models import CollectorResult, DiagnosticResult, Finding
from diagusb.core.rules import diagnose, RuleEngine
from diagusb.core import knowledge_base as kb


def create_mock_result(collector_id: str, data: list | dict, status: str = "ok") -> CollectorResult:
    """Crea un resultado de colector mock para pruebas."""
    return CollectorResult(
        schema_version=1,
        collector_id=collector_id,
        captured_at_utc=datetime.utcnow().isoformat(),
        query={"status": status, "duration_ms": 100, "timeout_seconds": 15},
        context={},
        metadata={},
        data=data,
        errors=[],
        notes=[],
    )


class TestRuleEngine:
    """Pruebas para RuleEngine."""

    def test_rule_engine_creation(self):
        """Verifica que el motor de reglas se inicialice correctamente."""
        engine = RuleEngine()
        assert "la_impresora_no_imprime" in engine._rules
        assert len(engine._rules["la_impresora_no_imprime"]) >= 5

    def test_check_spooler_running_ok(self):
        """Verifica que no se reporten errores cuando el spooler esta corriendo."""
        engine = RuleEngine()

        spooler_result = create_mock_result("spooler_service", {
            "spooler": {"name": "Spooler", "state": "Running", "display_name": "Print Spooler"},
            "required_services": [],
            "dependent_services": []
        })

        findings = engine._check_spooler_running([spooler_result])
        critical_findings = [f for f in findings if f.severity == "critical"]
        assert len(critical_findings) == 0

    def test_check_spooler_stopped(self):
        """Verifica que se detecte cuando el spooler esta detenido."""
        engine = RuleEngine()

        spooler_result = create_mock_result("spooler_service", {
            "spooler": {"name": "Spooler", "state": "Stopped", "display_name": "Print Spooler"},
            "required_services": [],
            "dependent_services": []
        })

        findings = engine._check_spooler_running([spooler_result])
        critical_findings = [f for f in findings if f.severity == "critical"]
        assert len(critical_findings) > 0
        assert "Spooler" in critical_findings[0].message

    def test_check_offline_printer(self):
        """Verifica que se detecten impresoras offline."""
        engine = RuleEngine()

        printer_result = create_mock_result("printers", [
            {
                "device_id": "HP-LaserJet",
                "name": "HP LaserJet Pro",
                "work_offline": True,
                "default": True,
            }
        ])

        findings = engine._check_offline_printers([printer_result])
        error_findings = [f for f in findings if f.severity == "error"]
        assert len(error_findings) > 0

    def test_check_printer_error_state(self):
        """Verifica que se detecten impresoras con estado de error."""
        engine = RuleEngine()

        printer_result = create_mock_result("printers", [
            {
                "device_id": "Canon-G3",
                "name": "Canon imageCLASS",
                "detected_error_state": 8,
                "work_offline": False,
                "default": False,
            }
        ])

        findings = engine._check_printer_error_state([printer_result])
        assert len(findings) > 0

        sin_error = create_mock_result("printers", [
            {
                "device_id": "PDF",
                "name": "Microsoft Print to PDF",
                "detected_error_state": 2,
                "work_offline": False,
                "default": False,
            }
        ])
        assert engine._check_printer_error_state([sin_error]) == []

    def test_stuck_jobs_detection(self):
        """Verifica la deteccion de trabajos atascados."""
        engine = RuleEngine()

        # Crear un trabajo antiguo (mas de 5 minutos)
        old_time = datetime.utcnow() - timedelta(hours=1)

        jobs_result = create_mock_result("print_jobs", [
            {
                "name": "Trabajo1",
                "document": "documento.pdf",
                "job_id": 1,
                "status_mask": 0,
                "time_submitted_utc": old_time.isoformat(),
            }
        ])

        findings = engine._check_stuck_jobs([jobs_result])
        warning_findings = [f for f in findings if f.severity == "warning"]
        assert len(warning_findings) > 0

    def test_diagnose_function(self):
        """Verifica la funcion principal diagnose()."""
        spooler_result = create_mock_result("spooler_service", {
            "spooler": {"name": "Spooler", "state": "Running"}
        })
        printer_result = create_mock_result("printers", [
            {"device_id": "Test", "name": "Test Printer", "detected_error_state": 0, "work_offline": False, "default": True}
        ])

        result = diagnose("la_impresora_no_imprime", [spooler_result, printer_result])

        assert isinstance(result, DiagnosticResult)
        assert result.symptom == "la_impresora_no_imprime"
        assert isinstance(result.findings, list)
        assert isinstance(result.recommendations, list)

    def test_driver_mismatch(self):
        """Verifica deteccion de drivers faltantes."""
        engine = RuleEngine()

        printers_result = create_mock_result("printers", [
            {"name": "Test Printer", "driver_name": "HP LaserJet 1010"}
        ])
        drivers_result = create_mock_result("printer_drivers", [
            {"name": "Canon Generic Driver"}
        ])

        findings = engine._check_driver_mismatch([printers_result, drivers_result])
        critical_findings = [f for f in findings if f.severity == "critical"]
        assert len(critical_findings) > 0

    def test_driver_mismatch_normalizado_y_ayuda(self):
        """El sufijo de version no genera falso positivo y la ayuda es la correcta."""
        engine = RuleEngine()
        printers_ok = create_mock_result("printers", [
            {"name": "Fax", "driver_name": "Microsoft Shared Fax Driver,4,Windows x64"}
        ])
        drivers_ok = create_mock_result("printer_drivers", [
            {"name": "Microsoft Shared Fax Driver"}
        ])
        assert engine._check_driver_mismatch([printers_ok, drivers_ok]) == []

        printers_falta = create_mock_result("printers", [
            {"name": "HP", "driver_name": "HP LaserJet 1010,3,Windows x64"}
        ])
        drivers_falta = create_mock_result("printer_drivers", [
            {"name": "Canon Generic Driver"}
        ])
        findings = engine._check_driver_mismatch([printers_falta, drivers_falta])
        assert len(findings) == 1
        assert findings[0].knowledge_id == "impresora_driver_faltante"
        kb.attach_knowledge(findings)
        assert kb.para_finding(findings[0])["id"] == "impresora_driver_faltante"

    def test_spooler_forma_real_en_lista(self):
        """El colector real entrega el spooler envuelto en una lista."""
        engine = RuleEngine()
        detenido = create_mock_result("spooler_service", [{
            "spooler": {"name": "Spooler", "state": "Stopped"}
        }])
        findings = engine._check_spooler_running([detenido])
        assert len(findings) == 1
        assert findings[0].severity == "critical"

    def test_network_adapter_vacio_no_es_critico(self):
        """Sin datos no se puede afirmar que los adaptadores esten deshabilitados."""
        engine = RuleEngine()
        vacio = create_mock_result("network_adapters", [], status="empty")
        assert engine._check_network_adapter_enabled([vacio]) == []
        assert engine._check_network_speed([vacio]) == []

    def test_network_adapter_wifi_arriba(self):
        """Un adaptador Wi-Fi nativo debe contar como conectado."""
        engine = RuleEngine()
        wifi = create_mock_result("network_adapters", [{
            "name": "Wi-Fi",
            "status": "Up",
            "state": "Up",
            "speed": "72 Mbps",
            "media_type": "Native 802.11",
        }])
        assert engine._check_network_adapter_enabled([wifi]) == []
        assert engine._check_network_speed([wifi]) == []

    def test_network_adapter_estados(self):
        """Distingue adaptadores deshabilitados de adaptadores desconectados."""
        engine = RuleEngine()
        deshabilitado = create_mock_result("network_adapters", [{
            "name": "Ethernet",
            "status": "Disabled",
        }])
        findings = engine._check_network_adapter_enabled([deshabilitado])
        assert len(findings) == 1
        assert findings[0].severity == "critical"

        desconectado = create_mock_result("network_adapters", [{
            "name": "Wi-Fi",
            "status": "Disconnected",
        }])
        findings = engine._check_network_adapter_enabled([desconectado])
        assert len(findings) == 1
        assert findings[0].severity == "warning"

    def test_conectividad_lista_exitosa_no_falsos(self):
        """Un ping ICMP bloqueado no debe ocultar que DNS e internet funcionan."""
        engine = RuleEngine()
        pruebas = create_mock_result("connectivity", [
            {"target": "192.168.1.1", "type": "gateway", "success": False},
            {"target": "8.8.8.8", "type": "icmp", "success": False},
            {"target": "google.com", "type": "dns", "success": True},
        ])
        assert engine._check_gateway_reachable([pruebas]) == []
        assert engine._check_internet_connectivity([pruebas]) == []

    def test_conectividad_todo_falla(self):
        """Si todas las pruebas fallan se reportan gateway e internet."""
        engine = RuleEngine()
        pruebas = create_mock_result("connectivity", [
            {"target": "192.168.1.1", "type": "gateway", "success": False},
            {"target": "8.8.8.8", "type": "icmp", "success": False},
            {"target": "google.com", "type": "dns", "success": False},
        ])
        gateway = engine._check_gateway_reachable([pruebas])
        internet = engine._check_internet_connectivity([pruebas])
        assert len(gateway) == 1 and gateway[0].severity == "error"
        assert len(internet) == 1 and internet[0].severity == "critical"

    def test_dns_servers_lista_por_interfaz(self):
        """La regla DNS debe leer la lista real por interfaz."""
        engine = RuleEngine()
        con_dns = create_mock_result("dns_servers", [
            {"interface_alias": "Wi-Fi", "dns_servers": ["8.8.8.8"]}
        ])
        assert engine._check_dns_config([con_dns]) == []

        sin_dns = create_mock_result("dns_servers", [
            {"interface_alias": "Wi-Fi", "dns_servers": []}
        ])
        findings = engine._check_dns_config([sin_dns])
        assert len(findings) == 1 and findings[0].severity == "error"

    def test_antivirus_y_firewall_en_listas(self):
        """Antivirus y firewall reales llegan como listas de productos/perfiles."""
        engine = RuleEngine()
        av_ok = create_mock_result("antivirus_status", [
            {"source": "Windows Defender", "enabled": True,
             "real_time_protection": True}
        ])
        assert engine._check_antivirus_enabled([av_ok]) == []
        av_off = create_mock_result("antivirus_status", [
            {"display_name": "Producto X", "enabled": False,
             "real_time_protection": False}
        ])
        findings = engine._check_antivirus_enabled([av_off])
        assert len(findings) == 1 and findings[0].severity == "critical"

        fw_ok = create_mock_result("firewall_status", [
            {"name": "Domain", "enabled": True},
            {"name": "Public", "enabled": False},
        ])
        assert engine._check_firewall_enabled([fw_ok]) == []
        fw_off = create_mock_result("firewall_status", [
            {"name": "Domain", "enabled": False},
            {"name": "Public", "enabled": False},
        ])
        findings = engine._check_firewall_enabled([fw_off])
        assert len(findings) == 1 and findings[0].severity == "error"

    def test_memoria_cpu_y_cola_de_disco_en_listas(self):
        """Memoria, CPU y cola de disco usan la forma real de sus colectores."""
        engine = RuleEngine()
        memoria = create_mock_result("memory_status", [
            {"physical_memory_usage_percent": 50.0}
        ])
        assert engine._check_memory_usage([memoria]) == []
        memoria_alta = create_mock_result("memory_status", [
            {"physical_memory_usage_percent": 96.0}
        ])
        findings = engine._check_memory_usage([memoria_alta])
        assert len(findings) == 1 and findings[0].severity == "critical"

        cpu = create_mock_result("system_performance", [{"cpu_load_percent": 40.0}])
        assert engine._check_high_cpu_usage([cpu]) == []
        cpu_alta = create_mock_result("system_performance", [{"cpu_load_percent": 100.0}])
        findings = engine._check_high_cpu_usage([cpu_alta])
        assert len(findings) == 1 and findings[0].severity == "warning"

        disco = create_mock_result("disk_performance", [
            {"disk": "0 C:", "current_disk_queue_length": 2, "percent_disk_time": 10}
        ])
        assert engine._check_disk_queue([disco]) == []
        disco_lleno = create_mock_result("disk_performance", [
            {"disk": "0 C:", "current_disk_queue_length": 50, "percent_disk_time": 95}
        ])
        findings = engine._check_disk_queue([disco_lleno])
        assert len(findings) == 1 and findings[0].severity == "warning"

    def test_disk_temperature_umbrales(self):
        """La temperatura SMART genera aviso y error sin falsos positivos."""
        engine = RuleEngine()

        def disco(temp, nombre="SSD"):
            return create_mock_result("physical_disks", [{
                "device_id": "0",
                "friendly_name": nombre,
                "media_type": "SSD",
                "operational_status": "OK",
                "temperature": temp,
            }])

        assert engine._check_disk_temperature([disco(45)]) == []
        assert engine._check_disk_temperature([disco(59.9)]) == []
        assert engine._check_disk_temperature([disco(None)]) == []
        assert engine._check_disk_temperature([disco(0)]) == []

        aviso = engine._check_disk_temperature([disco("60")])
        assert len(aviso) == 1
        assert aviso[0].severity == "warning"
        assert "60 °C" in aviso[0].message
        assert aviso[0].knowledge_id == "disco_caliente"

        critico = engine._check_disk_temperature([disco(75, "HDD viejo")])
        assert len(critico) == 1
        assert critico[0].severity == "error"
        assert "HDD viejo" in critico[0].message

        resultado = diagnose("disco_salud", [disco(72)])
        assert any(f.knowledge_id == "disco_caliente" for f in resultado.findings)

    def test_cpu_temperature_umbrales(self):
        """La temperatura del CPU avisa a 80 C y falla a 90 C."""
        engine = RuleEngine()

        def cpu(temp):
            return create_mock_result("cpu_temperature", {
                "available": True,
                "source": "librehardwaremonitor",
                "cpu_name": "AMD Ryzen 7 5800H",
                "max_temp_c": temp,
                "package_temp_c": temp,
                "max_core_temp_c": temp,
                "average_core_temp_c": temp,
                "sensor_count": 9,
            })

        assert engine._check_cpu_temperature([cpu(45)]) == []
        assert engine._check_cpu_temperature([cpu(79.9)]) == []
        assert engine._check_cpu_temperature([cpu(None)]) == []

        aviso = engine._check_cpu_temperature([cpu("80")])
        assert len(aviso) == 1
        assert aviso[0].severity == "warning"
        assert "80 °C" in aviso[0].message
        assert aviso[0].knowledge_id == "cpu_caliente"

        critico = engine._check_cpu_temperature([cpu(92.5)])
        assert len(critico) == 1
        assert critico[0].severity == "error"
        assert "Ryzen" in critico[0].message

        no_disponible = create_mock_result("cpu_temperature", {
            "available": False, "max_temp_c": 95,
        })
        assert engine._check_cpu_temperature([no_disponible]) == []

        resultado = diagnose("cpu_caliente", [cpu(91)])
        assert any(f.knowledge_id == "cpu_caliente" for f in resultado.findings)

    def test_bateria_desgaste_umbrales(self):
        """La bateria avisa con carga plena menor al 60% y falla bajo el 40%."""
        engine = RuleEngine()

        def bateria(design, full, carga=85, estado="Cargando", presente=True):
            return create_mock_result("battery", {
                "presente": presente,
                "carga_percent": carga,
                "battery_status": 6,
                "estado": estado,
                "design_capacity_mwh": design,
                "full_charge_capacity_mwh": full,
                "desgaste_percent": None,
                "ciclos": 320,
                "fuente_capacidad": "powercfg",
            })

        # notebook simulada con desgaste medio: warning
        aviso = engine._check_battery_health([bateria(96000, 52800)])
        assert len(aviso) == 1
        assert aviso[0].severity == "warning"
        assert "Desgaste de la batería" in aviso[0].message
        assert "45%" in aviso[0].message
        assert aviso[0].knowledge_id == "bateria_agotada"

        # notebook simulada muy desgastada: critico
        critico = engine._check_battery_health([bateria(96000, 33600)])
        assert len(critico) == 1
        assert critico[0].severity == "error"

        # bateria con poca perdida (el desgaste no dispara nada)
        assert engine._check_battery_health([bateria(96000, 92000)]) == []

        # sin capacidades utilizables no decide; tampoco un equipo sin bateria
        assert engine._check_battery_health([bateria(None, 52800)]) == []
        assert engine._check_battery_health(
            [bateria(96000, 52800, presente=False)]) == []

        # el diagnostico por sintoma usa la regla y la base de conocimiento
        resultado = diagnose("bateria_agotada", [bateria(96000, 30000)])
        assert any(f.knowledge_id == "bateria_agotada"
                   for f in resultado.findings)

    def test_network_speed_texto(self):
        """LinkSpeed llega como texto y debe interpretarse en Mbps."""
        engine = RuleEngine()
        rapidas = create_mock_result("network_adapters", [
            {"name": "Ethernet", "status": "Up", "speed": "1 Gbps"},
            {"name": "Wi-Fi", "status": "Up", "speed": "100 Mbps"},
        ])
        assert engine._check_network_speed([rapidas]) == []
        lenta = create_mock_result("network_adapters", [
            {"name": "Wi-Fi", "status": "Up", "speed": "10 Mbps"}
        ])
        findings = engine._check_network_speed([lenta])
        assert len(findings) == 1
        assert "10 Mbps" in findings[0].message

    def test_wifi_solo_red_conectada(self):
        """No debe advertir por redes vecinas debiles."""
        engine = RuleEngine()
        redes = create_mock_result("wifi_networks", [
            {"ssid": "MiRed", "connected": True, "signal": [80]},
            {"ssid": "Vecina", "connected": False, "signal": [10]},
        ])
        assert engine._check_wifi_signal([redes]) == []

        debil = create_mock_result("wifi_networks", [
            {"ssid": "MiRed", "connected": True, "signal": [30]},
            {"ssid": "Vecina", "connected": False, "signal": [90]},
        ])
        findings = engine._check_wifi_signal([debil])
        assert len(findings) == 1
        assert "MiRed" in findings[0].message and "Vecina" not in findings[0].message

        sin_marca = create_mock_result("wifi_networks", [
            {"ssid": "MiRed", "signal": [10]}
        ])
        assert engine._check_wifi_signal([sin_marca]) == []

    def test_sin_colector_demo(self):
        """Los colectores de produccion no deben incluir datos simulados."""
        ruta = (Path(__file__).parent.parent / "src" / "diagusb" / "packages"
                / "impresion" / "collectors" / "get_demo_printer.ps1")
        assert not ruta.exists()

    def test_antivirus_productstate_decode(self):
        """El productState de SecurityCenter2 se decodifica con las mascaras correctas."""
        base = (Path(__file__).parent.parent / "src" / "diagusb" / "packages"
                / "seguridad" / "collectors")
        for nombre in ("get_antivirus_status.ps1", "get_security_center_status.ps1"):
            texto = (base / nombre).read_text(encoding="utf-8")
            assert "-band 0xF000" in texto, nombre
            assert "-band 0x1000) -eq 0" not in texto, nombre
            assert "-shr 16" not in texto, nombre

    def test_wifi_parseo_espanol_sin_acentos(self):
        """El colector WiFi entiende netsh en espanol sin depender del encoding."""
        ruta = (Path(__file__).parent.parent / "src" / "diagusb" / "packages"
                / "wifi" / "collectors" / "get_wifi_networks.ps1")
        texto = ruta.read_text(encoding="utf-8")
        assert "Se\\u00f1al" in texto
        assert "Autenticaci(?:on|\\u00f3n)" in texto
        assert "Tipo de red" in texto and "Canal" in texto and "Tipo de radio" in texto
        assert all(ord(c) < 128 for c in texto)


def run_tests():
    """Ejecuta todas las pruebas."""
    test_instance = TestRuleEngine()

    tests = [
        ("test_rule_engine_creation", test_instance.test_rule_engine_creation),
        ("test_check_spooler_running_ok", test_instance.test_check_spooler_running_ok),
        ("test_check_spooler_stopped", test_instance.test_check_spooler_stopped),
        ("test_check_offline_printer", test_instance.test_check_offline_printer),
        ("test_check_printer_error_state", test_instance.test_check_printer_error_state),
        ("test_stuck_jobs_detection", test_instance.test_stuck_jobs_detection),
        ("test_diagnose_function", test_instance.test_diagnose_function),
        ("test_driver_mismatch", test_instance.test_driver_mismatch),
        ("test_driver_mismatch_normalizado_y_ayuda",
         test_instance.test_driver_mismatch_normalizado_y_ayuda),
        ("test_spooler_forma_real_en_lista",
         test_instance.test_spooler_forma_real_en_lista),
        ("test_network_adapter_vacio_no_es_critico",
         test_instance.test_network_adapter_vacio_no_es_critico),
        ("test_network_adapter_wifi_arriba",
         test_instance.test_network_adapter_wifi_arriba),
        ("test_network_adapter_estados",
         test_instance.test_network_adapter_estados),
        ("test_conectividad_lista_exitosa_no_falsos",
         test_instance.test_conectividad_lista_exitosa_no_falsos),
        ("test_conectividad_todo_falla",
         test_instance.test_conectividad_todo_falla),
        ("test_dns_servers_lista_por_interfaz",
         test_instance.test_dns_servers_lista_por_interfaz),
        ("test_antivirus_y_firewall_en_listas",
         test_instance.test_antivirus_y_firewall_en_listas),
        ("test_memoria_cpu_y_cola_de_disco_en_listas",
         test_instance.test_memoria_cpu_y_cola_de_disco_en_listas),
        ("test_disk_temperature_umbrales",
         test_instance.test_disk_temperature_umbrales),
        ("test_cpu_temperature_umbrales",
         test_instance.test_cpu_temperature_umbrales),
        ("test_bateria_desgaste_umbrales",
         test_instance.test_bateria_desgaste_umbrales),
        ("test_network_speed_texto", test_instance.test_network_speed_texto),
        ("test_wifi_solo_red_conectada",
         test_instance.test_wifi_solo_red_conectada),
        ("test_sin_colector_demo", test_instance.test_sin_colector_demo),
        ("test_antivirus_productstate_decode",
         test_instance.test_antivirus_productstate_decode),
        ("test_wifi_parseo_espanol_sin_acentos",
         test_instance.test_wifi_parseo_espanol_sin_acentos),
    ]

    passed = 0
    failed = 0

    print("Ejecutando pruebas del motor de reglas...")
    print("=" * 50)

    for name, test_func in tests:
        try:
            test_func()
            print(f"  [OK] {name}")
            passed += 1
        except AssertionError as e:
            print(f"  [FALLO] {name}: {e}")
            failed += 1
        except Exception as e:
            print(f"  [ERROR] {name}: {e}")
            failed += 1

    print("=" * 50)
    print(f"Resultados: {passed} pasadas, {failed} fallidas")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
