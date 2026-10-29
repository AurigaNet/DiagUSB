# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Motor de reglas de diagnostico para DiagUSB."""

import re
from datetime import datetime, timedelta, timezone
from typing import Any

from .models import CollectorResult, DiagnosticResult, Finding
from .context_aware import SystemContext, detect_context_from_observations, get_context_aware_rules
from . import knowledge_base as kb


def _normalizar_driver(nombre: Any) -> str:
    """Normaliza un nombre de driver quitando mayusculas, espacios y version."""
    texto = str(nombre or "").strip().casefold()
    texto = re.sub(r",\s*\d+\s*,\s*windows\s+[^,]+$", "", texto)
    return re.sub(r"[\s_]+", "", texto)


def _velocidad_mbps(valor: Any) -> float | None:
    """Convierte una velocidad tipo '1 Gbps' o '100 Mbps' a Mbps."""
    if valor is None or isinstance(valor, bool):
        return None
    if isinstance(valor, (int, float)):
        return float(valor) / 1_000_000
    texto = str(valor).strip().replace(",", ".")
    match = re.search(r"(\d+(?:\.\d+)?)\s*([KMG])?bps", texto, re.IGNORECASE)
    if not match:
        try:
            return float(texto) / 1_000_000
        except ValueError:
            return None
    factor = {"k": 0.001, "m": 1.0, "g": 1000.0}.get(
        (match.group(2) or "m").lower(), 1.0)
    return float(match.group(1)) * factor


class RuleEngine:
    """Motor de reglas para diagnosticos."""

    def __init__(self):
        self._rules: dict[str, list[callable]] = {}
        self._register_rules()

    def _register_rules(self):
        """Registra todas las reglas de diagnostico."""
        # ========== REGLAS DE IMPRESION ==========
        self.register("la_impresora_no_imprime", self._check_spooler_running)
        self.register("la_impresora_no_imprime", self._check_offline_printers)
        self.register("la_impresora_no_imprime", self._check_stuck_jobs)
        self.register("la_impresora_no_imprime", self._check_driver_mismatch)
        self.register("la_impresora_no_imprime", self._check_printer_error_state)
        self.register("la_impresora_no_imprime", self._check_port_connectivity)

        # ========== REGLAS DE RED ==========
        self.register("adaptador_red_no_funciona", self._check_network_adapter_enabled)
        self.register("no_hay_internet", self._check_network_adapter_enabled)
        self.register("no_hay_internet", self._check_gateway_reachable)
        self.register("no_hay_internet", self._check_internet_connectivity)
        self.register("red_lenta", self._check_network_speed)
        self.register("dns_no_responde", self._check_dns_config)

        # ========== REGLAS DE DISCO ==========
        self.register("disco_lleno", self._check_disk_space)
        self.register("disco_salud", self._check_disk_health)
        self.register("disco_salud", self._check_disk_temperature)

        # ========== REGLAS DE TEMPERATURA DEL CPU ==========
        self.register("cpu_caliente", self._check_cpu_temperature)
        self.register("ventilador_0_rpm_con_cpu_caliente", self._check_fan_health)

        # ========== REGLAS DE BATERIA ==========
        self.register("bateria_agotada", self._check_battery_health)

        # ========== REGLAS DE SERVICIOS ==========
        self.register("servicio_detenido", self._check_critical_services)
        self.register("servicios_fallando", self._check_service_failures)

        # ========== REGLAS DE SEGURIDAD ==========
        self.register("antivirus_apagado", self._check_antivirus_enabled)
        self.register("firewall_apagado", self._check_firewall_enabled)

        # ========== REGLAS DE MEMORIA ==========
        self.register("memoria_llena", self._check_memory_usage)
        self.register("sistema_lento", self._check_high_cpu_usage)
        self.register("sistema_lento", self._check_disk_queue)

        # ========== REGLAS DE ACTUALIZACIONES ==========
        self.register("updates_pendientes", self._check_pending_updates)
        self.register("updates_fallidos", self._check_pending_updates)
        self.register("windows_update_roto", self._check_pending_updates)

        # ========== REGLAS DE DRIVERS ==========
        self.register("driver_antiguo", self._check_outdated_drivers)
        self.register("driver_generico", self._check_outdated_drivers)

        # ========== REGLAS DE WIFI ==========
        self.register("wifi_no_conecta", self._check_wifi_signal)
        self.register("wifi_lento", self._check_wifi_signal)
        self.register("wifi_perdida", self._check_wifi_signal)

        # ========== REGLAS DE EVENTOS ==========
        self.register("blue_screen", self._check_bsod_events)
        self.register("error_del_sistema", self._check_bsod_events)
        self.register("apagado_inesperado", self._check_bsod_events)
        self.register("error_del_sistema", self._check_critical_events)
        self.register("apagado_inesperado", self._check_critical_events)

        # ========== REGLAS DE SINTOMAS DE SOPORTE ==========
        self.register("disco_lento", self._check_disk_slow)
        self.register("proceso_alto_cpu", self._check_process_high_cpu)
        self.register("seguridad_comprometida", self._check_security_compromised)
        self.register("servicio_no_inicia", self._check_service_wont_start)

        # ========== REGLAS DE RED, PUERTOS Y PERIFERICOS ==========
        self.register("puerto_expuesto", self._check_exposed_ports)
        self.register("equipos_red_no_visibles", self._check_lan_visibility)
        self.register("trafico_red_alterado", self._check_suspicious_traffic)
        self.register("gateway_no_responde", self._check_gateway_unreachable)
        self.register("dns_inestable", self._check_dns_instability)
        self.register("teclado_no_responde", self._check_keyboard)
        self.register("mouse_no_responde", self._check_pointing_device)

    def register(self, symptom: str, rule_func: callable):
        """Registra una regla para un sintoma especifico."""
        if symptom not in self._rules:
            self._rules[symptom] = []
        self._rules[symptom].append(rule_func)

    def evaluate(self, symptom: str, observations: list[CollectorResult]) -> list[Finding]:
        """Evalua todas las reglas para un sintoma dado."""
        findings = []
        rules = self._rules.get(symptom, [])
        for rule in rules:
            try:
                result = rule(observations)
            except Exception:
                continue
            if isinstance(result, Finding):
                findings.append(result)
            elif isinstance(result, list):
                findings.extend(result)
        return findings

    def _find_collector(self, observations: list[CollectorResult], collector_id: str) -> CollectorResult | None:
        """Busca un collector por su ID en las observaciones."""
        for obs in observations:
            if obs.collector_id == collector_id:
                return obs
        return None

    def _get_data(self, result: CollectorResult | None) -> list | dict:
        """Obtiene los datos de un resultado de colector."""
        if not result:
            return []
        # Verificar status - puede ser dict o objeto con atributo
        status = None
        if hasattr(result, 'query') and result.query:
            if isinstance(result.query, dict):
                status = result.query.get('status')
            else:
                status = getattr(result.query, 'status', None)
        if status and status != "ok":
            return [] if isinstance(result.data, list) else {} if result.data else {}
        return result.data if isinstance(result.data, (list, dict)) else []

    # ========== REGLAS DE IMPRESION ==========

    def _check_spooler_running(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica que el servicio Spooler este en ejecucion."""
        result = self._find_collector(observations, "spooler_service")
        if not result:
            return []
        findings = []
        data = self._primer_dict(self._get_data(result))
        if data:
            spooler = data.get("spooler", data)
            if isinstance(spooler, dict) and spooler.get("state") not in (None, "Running"):
                findings.append(Finding(
                    severity="critical",
                    collector_id="spooler_service",
                    message="El servicio Spooler no está en ejecución",
                    details={"state": spooler.get("state"), "service": "Spooler"}
                ))
        return findings

    def _check_offline_printers(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica impresoras offline."""
        result = self._find_collector(observations, "printers")
        if not result:
            return []
        findings = []
        printers = self._get_data(result) if isinstance(self._get_data(result), list) else []
        for printer in printers:
            if printer.get("work_offline") and printer.get("default"):
                findings.append(Finding(
                    severity="error",
                    collector_id="printers",
                    message="La impresora predeterminada está offline",
                    details={"printer": printer.get("name", printer.get("device_id", ""))}
                ))
        return findings

    def _check_stuck_jobs(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica trabajos atascados en la cola."""
        result = self._find_collector(observations, "print_jobs")
        if not result:
            return []
        findings = []
        jobs = self._get_data(result) if isinstance(self._get_data(result), list) else []
        now = datetime.now(timezone.utc)
        stuck_threshold = now - timedelta(minutes=5)
        for job in jobs:
            time_str = job.get("time_submitted_utc", "")
            if time_str:
                try:
                    time_str = time_str.replace("Z", "+00:00")
                    submitted = datetime.fromisoformat(time_str)
                    if submitted.tzinfo is None:
                        submitted = submitted.replace(tzinfo=timezone.utc)
                    if submitted < stuck_threshold:
                        findings.append(Finding(
                            severity="warning",
                            collector_id="print_jobs",
                            message="Hay trabajos atascados en la cola",
                            details={"job_id": job.get("job_id"), "document": job.get("document")}
                        ))
                        break
                except Exception:
                    continue
        return findings

    def _check_driver_mismatch(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica drivers faltantes."""
        printers_result = self._find_collector(observations, "printers")
        drivers_result = self._find_collector(observations, "printer_drivers")
        if not printers_result or not drivers_result:
            return []
        findings = []
        printers = self._get_data(printers_result) if isinstance(self._get_data(printers_result), list) else []
        drivers = self._get_data(drivers_result) if isinstance(self._get_data(drivers_result), list) else []
        available_drivers = {
            _normalizar_driver(d.get("name", "")) for d in drivers
            if _normalizar_driver(d.get("name", ""))
        }
        for printer in printers:
            driver = printer.get("driver_name", "")
            driver_normalizado = _normalizar_driver(driver)
            if driver_normalizado and driver_normalizado not in available_drivers:
                findings.append(Finding(
                    severity="critical",
                    collector_id="printers",
                    knowledge_id="impresora_driver_faltante",
                    message="Driver no encontrado para la impresora",
                    details={"printer": printer.get("name", ""), "driver": driver}
                ))
        return findings

    def _check_printer_error_state(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica estados de error en impresoras."""
        result = self._find_collector(observations, "printers")
        if not result:
            return []
        findings = []
        printers = self._get_data(result) if isinstance(self._get_data(result), list) else []
        for printer in printers:
            estado = printer.get("detected_error_state", 0)
            if estado not in (0, 2):
                findings.append(Finding(
                    severity="error",
                    collector_id="printers",
                    message="Estado de error detectado en impresora",
                    details={"printer": printer.get("name", ""), "error_state": estado}
                ))
        return findings

    def _check_port_connectivity(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica puertos de impresion TCP/IP."""
        result = self._find_collector(observations, "printer_ports")
        if not result:
            return []
        findings = []
        ports = self._get_data(result) if isinstance(self._get_data(result), list) else []
        for port in ports:
            if port.get("host_address") and not port.get("port_number"):
                findings.append(Finding(
                    severity="warning",
                    collector_id="printer_ports",
                    message="Puerto TCP/IP sin número de puerto configurado",
                    details={"port": port.get("name"), "host": port.get("host_address")}
                ))
        return findings

    # ========== REGLAS DE RED ==========

    def _check_network_adapter_enabled(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica que exista al menos un adaptador de red conectado."""
        result = self._find_collector(observations, "network_adapters")
        if not result:
            return []
        adapters = self._lista_dicts(self._get_data(result))
        if not adapters:
            return []
        if any(a.get("status") == "Up" or a.get("state") == "Up" for a in adapters):
            return []

        deshabilitados = [a for a in adapters if a.get("status") == "Disabled"]
        if len(deshabilitados) == len(adapters):
            return [Finding(
                severity="critical",
                collector_id="network_adapters",
                message="Todos los adaptadores de red están deshabilitados",
                details={"total_adapters": len(adapters), "enabled": 0}
            )]

        return [Finding(
            severity="warning",
            collector_id="network_adapters",
            message="Ningún adaptador de red tiene conexión activa",
            details={
                "total_adapters": len(adapters),
                "enabled": 0,
                "status": sorted({str(a.get("status") or "desconocido")
                                  for a in adapters}),
            }
        )]

    def _check_gateway_reachable(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica que el gateway sea alcanzable."""
        result = self._find_collector(observations, "connectivity")
        if not result:
            return []
        pruebas = self._lista_dicts(self._get_data(result))
        if not pruebas or any(t.get("success") is True for t in pruebas):
            return []
        gateways = [t for t in pruebas if str(t.get("type") or "").lower() == "gateway"]
        if not gateways or any(t.get("success") is not False for t in gateways):
            return []
        gateway = gateways[0]
        return [Finding(
            severity="error",
            collector_id="connectivity",
            message="El gateway no es alcanzable",
            details={"gateway": gateway.get("target"),
                     "latency": gateway.get("latency_ms")}
        )]

    def _check_internet_connectivity(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica conectividad a internet."""
        result = self._find_collector(observations, "connectivity")
        if not result:
            return []
        pruebas = self._lista_dicts(self._get_data(result))
        internet = [t for t in pruebas
                    if str(t.get("type") or "").lower() in ("icmp", "dns")]
        if not internet or any(t.get("success") is True for t in internet):
            return []
        fallos = [t for t in internet if t.get("success") is False]
        if len(fallos) != len(internet):
            return []
        return [Finding(
            severity="critical",
            collector_id="connectivity",
            message="No hay conectividad a internet",
            details={"targets": [t.get("target") for t in fallos]}
        )]

    def _check_network_speed(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica velocidad del adaptador de red."""
        result = self._find_collector(observations, "network_adapters")
        if not result:
            return []
        findings = []
        for adapter in self._lista_dicts(self._get_data(result)):
            if adapter.get("status") != "Up":
                continue
            speed = _velocidad_mbps(adapter.get("speed"))
            if speed is not None and 0 < speed < 20:  # Menos de 20 Mbps
                findings.append(Finding(
                    severity="warning",
                    collector_id="network_adapters",
                    message=f"Adaptador de red con velocidad baja: {speed:g} Mbps",
                    details={"adapter": adapter.get("name"), "speed_mbps": speed}
                ))
        return findings

    def _check_dns_config(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica configuracion de DNS."""
        result = self._find_collector(observations, "dns_servers")
        if not result:
            return []
        interfaces = self._lista_dicts(self._get_data(result))
        if not interfaces:
            return []
        if any(i.get("dns_servers") for i in interfaces):
            return []
        return [Finding(
            severity="error",
            collector_id="dns_servers",
            message="No hay servidores DNS configurados",
            details={"interfaces": [i.get("interface_alias") for i in interfaces]}
        )]

    # ========== REGLAS DE DISCO ==========

    def _check_disk_space(self, observations: list[CollectorResult], config: dict = None) -> list[Finding]:
        """Verifica espacio en disco con umbrales adaptados al contexto."""
        result = self._find_collector(observations, "logical_disks")
        if not result:
            return []

        # Obtener contexto del sistema
        context = detect_context_from_observations(observations)

        # Obtener umbrales del contexto o usar valores por defecto
        warning_threshold = 20
        critical_threshold = 10

        if context:
            system_type = context.system_type
            is_old = context.is_old_machine()
            context_config = get_context_aware_rules(system_type, is_old)
            warning_threshold = context_config.get("disk_space_warning", warning_threshold)
            critical_threshold = context_config.get("disk_space_critical", critical_threshold)
        elif config:
            warning_threshold = config.get("disk_space_warning", warning_threshold)
            critical_threshold = config.get("disk_space_critical", critical_threshold)

        findings = []
        disks = self._get_data(result) if isinstance(self._get_data(result), list) else []
        for disk in disks:
            free_percent = disk.get("free_percent", 100)
            if free_percent < critical_threshold:
                findings.append(Finding(
                    severity="critical",
                    collector_id="logical_disks",
                    message=f"Espacio crítico en {disk.get('device_id')}: {free_percent:.1f}% libre",
                    details={"device_id": disk.get("device_id"), "free_gb": disk.get("free_gb"), "total_gb": disk.get("total_gb")}
                ))
            elif free_percent < warning_threshold:
                findings.append(Finding(
                    severity="warning",
                    collector_id="logical_disks",
                    message=f"Espacio limitado en disco {disk.get('device_id')}: {free_percent:.1f}% libre",
                    details={"device_id": disk.get("device_id")}
                ))
        return findings

    def _check_disk_health(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica salud del disco fisico."""
        result = self._find_collector(observations, "physical_disks")
        if not result:
            return []
        findings = []
        disks = self._get_data(result) if isinstance(self._get_data(result), list) else []
        for disk in disks:
            if disk.get("operational_status") != "OK":
                findings.append(Finding(
                    severity="error",
                    collector_id="physical_disks",
                    message=f"Disco con estado no óptimo: {disk.get('friendly_name')}",
                    details={"status": disk.get("operational_status")}
                ))
        return findings

    def _check_disk_temperature(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica la temperatura SMART de los discos fisicos."""
        result = self._find_collector(observations, "physical_disks")
        if not result:
            return []
        data = self._get_data(result)
        disks = data if isinstance(data, list) else []
        findings = []
        for disk in disks:
            if not isinstance(disk, dict):
                continue
            raw = disk.get("temperature")
            if raw is None or isinstance(raw, bool):
                continue
            try:
                temperature = float(raw)
            except (TypeError, ValueError):
                continue
            if not 0 < temperature < 120:
                continue
            if temperature >= 70:
                severity = "error"
                estado = "crítica"
            elif temperature >= 60:
                severity = "warning"
                estado = "elevada"
            else:
                continue
            name = disk.get("friendly_name") or f"Disco {disk.get('device_id') or '?'}"
            findings.append(Finding(
                severity=severity,
                collector_id="physical_disks",
                message=f"Temperatura {estado} del disco {name}: {temperature:.0f} °C",
                details={
                    "device_id": disk.get("device_id"),
                    "temperature_c": round(temperature, 1),
                    "media_type": disk.get("media_type"),
                    "bus_type": disk.get("bus_type"),
                },
                knowledge_id="disco_caliente",
            ))
        return findings

    def _check_cpu_temperature(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica la temperatura del CPU leida desde LibreHardwareMonitor."""
        result = self._find_collector(observations, "cpu_temperature")
        if not result:
            return []
        data = self._primer_dict(self._get_data(result))
        if not data or data.get("available") is False:
            return []

        valores = []
        for key in ("max_temp_c", "package_temp_c", "max_core_temp_c"):
            raw = data.get(key)
            if raw is None or isinstance(raw, bool):
                continue
            try:
                valores.append(float(raw))
            except (TypeError, ValueError):
                continue
        valores = [v for v in valores if 0 < v < 130]
        if not valores:
            return []

        temperature = max(valores)
        if temperature >= 90:
            severity = "error"
            estado = "crítica"
        elif temperature >= 80:
            severity = "warning"
            estado = "elevada"
        else:
            return []

        cpu_name = str(data.get("cpu_name") or "").strip()
        etiqueta = f" ({cpu_name})" if cpu_name else ""
        return [Finding(
            severity=severity,
            collector_id="cpu_temperature",
            message=f"Temperatura {estado} del CPU{etiqueta}: {temperature:.0f} °C",
            details={
                "cpu_name": cpu_name,
                "temperature_c": round(temperature, 1),
                "package_temp_c": data.get("package_temp_c"),
                "max_core_temp_c": data.get("max_core_temp_c"),
                "average_core_temp_c": data.get("average_core_temp_c"),
                "sensor_count": data.get("sensor_count"),
                "source": data.get("source"),
            },
            knowledge_id="cpu_caliente",
        )]

    UMBRAL_CPU_VENTILADOR_C = 70

    def _check_fan_health(self, observations: list[CollectorResult]) -> list[Finding]:
        """CPU caliente con ventilador sin girar: es un indicio, no una prueba.

        Con el CPU a UMBRAL_CPU_VENTILADOR_C o mas avisa si ningun ventilador
        marca RPM mayores a 0 o si el sensor del CPU marca 0 RPM. Nunca es
        error ni critico: un 0 RPM puede ser un sensor sin conectar.
        """
        cpu_result = self._find_collector(observations, "cpu_temperature")
        fan_result = self._find_collector(observations, "fan_speeds")
        if not cpu_result or not fan_result:
            return []
        cpu = self._primer_dict(self._get_data(cpu_result))
        fan = self._primer_dict(self._get_data(fan_result))
        if not cpu or cpu.get("available") is False:
            return []
        if not fan or fan.get("available") is False:
            return []

        valores = []
        for key in ("max_temp_c", "package_temp_c", "max_core_temp_c"):
            raw = cpu.get(key)
            if raw is None or isinstance(raw, bool):
                continue
            try:
                valores.append(float(raw))
            except (TypeError, ValueError):
                continue
        valores = [v for v in valores if 0 < v < 130]
        if not valores:
            return []
        temperature = max(valores)
        if temperature < self.UMBRAL_CPU_VENTILADOR_C:
            return []

        def _rpm(valor):
            if valor is None or isinstance(valor, bool):
                return None
            try:
                return float(valor)
            except (TypeError, ValueError):
                return None

        lecturas = [(str(s.get("name") or ""), _rpm(s.get("rpm")))
                    for s in self._lista_dicts(fan.get("sensors"))]
        if not lecturas:
            crudos = fan.get("fan_rpms")
            if isinstance(crudos, (int, float)) and not isinstance(crudos, bool):
                crudos = [crudos]
            if isinstance(crudos, list):
                lecturas = [("", _rpm(v)) for v in crudos]
        girando = [n for n, r in lecturas if r is not None and r > 0]
        cpu_en_cero = any(
            r is not None and r == 0
            for n, r in lecturas
            if re.search(r"cpu|processor", n, re.IGNORECASE)
        )
        if girando and not cpu_en_cero:
            return []

        severidad = "warning"
        if girando:
            detalle = "el sensor del CPU marca 0 RPM"
        else:
            detalle = "ning\u00fan ventilador marca RPM mayores a 0"
        return [Finding(
            severity=severidad,
            collector_id="fan_speeds",
            message=(f"CPU a {temperature:.0f} \u00b0C y {detalle}: "
                     "puede ser un ventilador detenido o un sensor sin conectar"),
            details={
                "temperature_c": round(temperature, 1),
                "umbral_c": self.UMBRAL_CPU_VENTILADOR_C,
                "ventiladores_girando": len(girando),
                "lecturas": [{"name": n, "rpm": r} for n, r in lecturas],
                "sensor_count": fan.get("sensor_count"),
                "source": fan.get("source"),
            },
            knowledge_id="ventilador_0_rpm_con_cpu_caliente",
        )]

    def _check_battery_health(self, observations: list[CollectorResult]) -> list[Finding]:
        """Evalua el desgaste de la bateria: carga plena frente a diseno.

        Con carga plena menor al 60 % de la capacidad de diseno es aviso y
        con menos del 40 % es critico. La deteccion previa de capacidades
        oculta el paquete en equipos sin bateria; el colector tambien
        declara ``presente`` por si el paquete corre igualmente.
        """
        result = self._find_collector(observations, "battery")
        if not result:
            return []
        data = self._primer_dict(self._get_data(result))
        if not data or data.get("presente") is not True:
            return []

        def _numero(clave):
            valor = data.get(clave)
            if valor is None or isinstance(valor, bool):
                return None
            try:
                numero = float(valor)
            except (TypeError, ValueError):
                return None
            return numero if numero > 0 else None

        diseno = _numero("design_capacity_mwh")
        plena = _numero("full_charge_capacity_mwh")
        if not diseno or not plena:
            return []
        relacion = plena / diseno
        if relacion >= 0.6:
            return []
        severity = "error" if relacion < 0.4 else "warning"
        desgaste = max(0.0, (1.0 - relacion) * 100.0)
        estado = "crítico" if severity == "error" else "elevado"
        return [Finding(
            severity=severity,
            collector_id="battery",
            message=("Desgaste de la batería: "
                     f"{desgaste:.0f}% "
                     f"(carga plena {plena:.0f} mWh de {diseno:.0f} mWh de diseño, "
                     f"desgaste {estado})"),
            details={
                "charge_percent": data.get("carga_percent"),
                "battery_status": data.get("battery_status"),
                "estado": data.get("estado"),
                "design_capacity_mwh": round(diseno, 1),
                "full_charge_capacity_mwh": round(plena, 1),
                "desgaste_percent": round(desgaste, 1),
                "ciclos": data.get("ciclos"),
                "fuente_capacidad": data.get("fuente_capacidad"),
            },
            knowledge_id="bateria_agotada",
        )]

    # ========== REGLAS DE SERVICIOS ==========

    @staticmethod
    def _extract_services(data) -> list[dict]:
        """Normaliza la salida de los colectores de servicios a una lista plana.

        Los colectores devuelven listas con un dict envoltorio
        [{"critical_services": [...]}] o dicts {"failed_services": [...]}.
        """
        items = data if isinstance(data, list) else ([data] if isinstance(data, dict) else [])
        flat: list[dict] = []
        for item in items:
            if not isinstance(item, dict):
                continue
            if "name" in item or "state" in item:
                flat.append(item)
                continue
            for key in ("critical_services", "failed_services", "alerts", "services"):
                value = item.get(key)
                if isinstance(value, list):
                    flat.extend(s for s in value if isinstance(s, dict))
        return flat

    def _check_critical_services(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica servicios críticos configurados en Automático que están detenidos."""
        result = self._find_collector(observations, "critical_services")
        if not result:
            return []
        findings = []
        services = self._extract_services(self._get_data(result))
        for svc in services:
            start_mode = (svc.get("start_mode") or "").lower()
            state = svc.get("state") or ""
            if start_mode == "auto" and state.lower() != "running":
                name = svc.get("display_name") or svc.get("name") or "desconocido"
                findings.append(Finding(
                    severity="error",
                    collector_id="critical_services",
                    message=f"Servicio crítico detenido: {name} (estado: {state or 'desconocido'})",
                    details={
                        "name": svc.get("name"),
                        "display_name": svc.get("display_name"),
                        "state": state,
                        "start_mode": svc.get("start_mode"),
                    }
                ))
        return findings

    def _check_service_failures(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica servicios configurados en Automático que no están en ejecución."""
        result = self._find_collector(observations, "service_failures")
        if not result:
            return []
        findings = []
        for failure in self._extract_services(self._get_data(result)):
            start_mode = (failure.get("start_mode") or "").lower()
            state = failure.get("state") or ""
            if start_mode != "auto" or state.lower() == "running":
                continue
            name = failure.get("display_name") or failure.get("name") or "desconocido"
            exit_code = failure.get("exit_code")
            findings.append(Finding(
                severity="error",
                collector_id="service_failures",
                message=f"Servicio detenido: {name} está configurado en Automático pero no está en ejecución (estado: {state})",
                details={
                    "name": failure.get("name"),
                    "display_name": failure.get("display_name"),
                    "state": state,
                    "start_mode": failure.get("start_mode"),
                    "exit_code": exit_code,
                }
            ))
        return findings

    # ========== REGLAS DE SEGURIDAD ==========

    def _check_antivirus_enabled(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica que el antivirus este habilitado."""
        result = self._find_collector(observations, "antivirus_status")
        if not result:
            return []
        productos = self._lista_dicts(self._get_data(result))
        if not productos:
            return []
        if any(p.get("enabled") is True or p.get("real_time_protection") is True
               for p in productos):
            return []
        return [Finding(
            severity="critical",
            collector_id="antivirus_status",
            message="Antivirus deshabilitado",
            details={
                "products": [p.get("display_name") or p.get("source")
                             for p in productos],
                "real_time": any(p.get("real_time_protection") is False
                                 for p in productos),
            }
        )]

    def _check_firewall_enabled(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica que el firewall este habilitado."""
        result = self._find_collector(observations, "firewall_status")
        if not result:
            return []
        perfiles = self._lista_dicts(self._get_data(result))
        if not perfiles:
            return []
        habilitados = [p for p in perfiles if p.get("enabled") is True]
        if habilitados:
            return []
        return [Finding(
            severity="error",
            collector_id="firewall_status",
            message="Todos los perfiles de firewall están deshabilitados",
            details={"enabled_profiles": 0,
                     "profiles": [p.get("name") for p in perfiles]}
        )]

    # ========== REGLAS DE MEMORIA ==========

    def _check_memory_usage(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica uso de memoria."""
        result = self._find_collector(observations, "memory_status")
        if not result:
            return []
        data = self._primer_dict(self._get_data(result))
        if not data:
            return []
        usage_percent = data.get("physical_memory_usage_percent")
        if usage_percent is None:
            usage_percent = data.get("memory_usage_percent")
        try:
            usage_percent = float(usage_percent)
        except (TypeError, ValueError):
            return []
        if usage_percent > 95:
            return [Finding(
                severity="critical",
                collector_id="memory_status",
                message=f"Memoria casi llena: {usage_percent:.1f}% en uso",
                details={"usage_percent": usage_percent}
            )]
        if usage_percent > 85:
            return [Finding(
                severity="warning",
                collector_id="memory_status",
                message=f"Memoria alta: {usage_percent:.1f}% en uso",
                details={"usage_percent": usage_percent}
            )]
        return []

    def _check_high_cpu_usage(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica uso alto de CPU."""
        result = self._find_collector(observations, "system_performance")
        if not result:
            return []
        data = self._primer_dict(self._get_data(result))
        if not data:
            return []
        try:
            cpu_usage = float(data.get("cpu_load_percent"))
        except (TypeError, ValueError):
            return []
        if cpu_usage > 95:
            return [Finding(
                severity="warning",
                collector_id="system_performance",
                message=f"Uso alto de CPU: {cpu_usage:.1f}%",
                details={"cpu_usage": cpu_usage}
            )]
        return []

    def _check_disk_queue(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica cola de disco."""
        result = self._find_collector(observations, "disk_performance")
        if not result:
            return []
        findings = []
        for data in self._lista_dicts(self._get_data(result)):
            try:
                queue = float(data.get("current_disk_queue_length"))
                percent = float(data.get("percent_disk_time") or 0)
            except (TypeError, ValueError):
                continue
            if queue > 20 and percent > 80:
                findings.append(Finding(
                    severity="warning",
                    collector_id="disk_performance",
                    message=f"Cola de disco alta: {queue:g}",
                    details={"disk": data.get("disk"), "queue_length": queue,
                             "percent_disk_time": percent}
                ))
        return findings

    # ========== REGLAS DE ACTUALIZACIONES / DRIVERS / WIFI / EVENTOS ==========

    @staticmethod
    def _primer_dict(data) -> dict | None:
        """Primer dict util de la salida de un colector (a veces va envuelta en lista)."""
        if isinstance(data, dict):
            return data
        if isinstance(data, list):
            for item in data:
                if isinstance(item, dict):
                    return item
        return None

    @staticmethod
    def _lista_dicts(data) -> list[dict]:
        """Salida de un colector como lista de diccionarios."""
        if isinstance(data, dict):
            return [data]
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        return []

    @staticmethod
    def _parse_timestamp(value) -> datetime | None:
        """Parsea timestamps ISO8601 tolerando sufijo Z y formatos raros."""
        if not value:
            return None
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            return None

    def _check_pending_updates(self, observations: list[CollectorResult]) -> list[Finding]:
        """Actualizaciones de Windows pendientes de instalar."""
        result = self._find_collector(observations, "pending_updates")
        if not result:
            return []
        d = self._primer_dict(self._get_data(result))
        if not d or d.get("status") != "ok":
            return []
        try:
            n = int(d.get("actualizaciones_pendientes") or 0)
        except (TypeError, ValueError):
            n = 0
        if n <= 0:
            return []
        pendientes = [u for u in (d.get("actualizaciones") or []) if isinstance(u, dict)]
        criticas = [
            u for u in pendientes
            if str(u.get("importancia") or "").lower().translate(
                str.maketrans("áéíóúü", "aeiouu")) in ("critical", "critica")
        ]
        return [Finding(
            severity="error" if criticas else "warning",
            collector_id="pending_updates",
            message=(f"{n} actualización(es) de Windows pendientes de instalar"
                     + (f" ({len(criticas)} crítica/s)" if criticas else "")),
            details={
                "pendientes": n,
                "criticas": len(criticas),
                "primeras": [str(u.get("kb") or u.get("titulo") or "")[:80] for u in pendientes[:5]],
            },
        )]

    def _check_outdated_drivers(self, observations: list[CollectorResult]) -> list[Finding]:
        """Drivers genericos, con mas de 5 anios o con advertencia (triangulo amarillo)."""
        result = self._find_collector(observations, "outdated_drivers")
        if not result:
            return []
        data = self._get_data(result)
        drivers = [x for x in data if isinstance(x, dict)] if isinstance(data, list) else []
        if not drivers:
            return []

        findings: list[Finding] = []

        con_adv = [d for d in drivers if "advertencia" in (d.get("reasons") or [])]
        genericos = [d for d in drivers if "generico" in (d.get("reasons") or [])]
        antiguos = [d for d in drivers if "antiguo" in (d.get("reasons") or [])]

        if con_adv:
            ejemplos = []
            for d in con_adv[:5]:
                etq = str(d.get("device_name") or "")
                cod = d.get("config_error_code")
                if cod:
                    etq += f" (código {cod}" + (
                        f": {d.get('config_error_text')})" if d.get("config_error_text") else ")")
                ejemplos.append(etq[:90])
            findings.append(Finding(
                severity="error",
                collector_id="outdated_drivers",
                message=f"{len(con_adv)} dispositivo(s) con advertencia en el "
                        f"Administrador de dispositivos",
                details={
                    "total": len(con_adv),
                    "codigos": sorted({int(d.get("config_error_code") or 0)
                                       for d in con_adv}),
                    "primeros": ejemplos,
                },
            ))

        if genericos or antiguos:
            n_gen, n_ant = len(genericos), len(antiguos)
            if n_gen and n_ant:
                mensaje = (f"{n_gen} driver(s) genéricos y {n_ant} con más de 5 años "
                           f"sin actualizar")
            elif n_gen:
                mensaje = f"{n_gen} driver(s) genéricos (driver básico de Windows)"
            else:
                mensaje = f"{n_ant} driver(s) con más de 5 años sin actualizar"
            destacados = (genericos + antiguos)[:5]
            findings.append(Finding(
                severity="warning",
                collector_id="outdated_drivers",
                message=mensaje,
                details={
                    "total": n_gen + n_ant,
                    "genericos": n_gen,
                    "antiguos": n_ant,
                    "primeros": [str(d.get("device_name") or "")[:70]
                                 for d in destacados],
                },
            ))

        return findings

    def _check_wifi_signal(self, observations: list[CollectorResult]) -> list[Finding]:
        """Redes WiFi con senal debil (menos del 40% en netsh)."""
        result = self._find_collector(observations, "wifi_networks")
        if not result:
            return []
        redes = self._lista_dicts(self._get_data(result))
        if not redes or not any("connected" in red for red in redes):
            return []
        debiles = []
        for red in redes:
            if red.get("connected") is not True:
                continue
            sig = red.get("signal")
            vals = [s for s in sig if isinstance(s, int)] if isinstance(sig, list) else (
                [sig] if isinstance(sig, int) else [])
            if vals and max(vals) < 40:
                debiles.append(f"{red.get('ssid')} ({max(vals)}%)")
        if not debiles:
            return []
        return [Finding(
            severity="warning",
            collector_id="wifi_networks",
            message=f"Señal WiFi débil en {len(debiles)} red(es): " + ", ".join(debiles[:4]),
            details={"redes": debiles[:8]},
        )]

    def _check_bsod_events(self, observations: list[CollectorResult]) -> list[Finding]:
        """Pantallazos azules (BSOD) recientes."""
        result = self._find_collector(observations, "bsod_events")
        if not result:
            return []
        data = self._get_data(result)
        if not isinstance(data, list):
            return []
        ahora = datetime.now(timezone.utc)
        hace_7 = ahora - timedelta(days=7)
        hace_30 = ahora - timedelta(days=30)
        recientes = 0
        ultimo = None
        en_30 = 0
        for ev in data:
            if not isinstance(ev, dict):
                continue
            ts = self._parse_timestamp(ev.get("time_created"))
            if not ts:
                continue
            if ts >= hace_7:
                recientes += 1
                ultimo = ts
            elif ts >= hace_30:
                en_30 += 1
        if recientes:
            return [Finding(
                severity="error",
                collector_id="bsod_events",
                message=f"{recientes} pantallazo(s) azul (BSOD) en los últimos 7 días",
                details={"recientes_7d": recientes,
                         "ultimo": ultimo.isoformat() if ultimo else None},
            )]
        if en_30:
            return [Finding(
                severity="warning",
                collector_id="bsod_events",
                message=f"{en_30} pantallazo(s) azul (BSOD) en los últimos 30 días (sin recientes)",
                details={"ultimos_30d": en_30},
            )]
        return []

    def _check_critical_events(self, observations: list[CollectorResult]) -> list[Finding]:
        """Eventos críticos del sistema (nivel Crítico/Error) recientes."""
        result = self._find_collector(observations, "critical_events")
        if not result:
            return []
        data = self._get_data(result)
        if not isinstance(data, list):
            return []
        hace_7 = datetime.now(timezone.utc) - timedelta(days=7)
        n_criticos = 0
        n_errores = 0
        for ev in data:
            if not isinstance(ev, dict):
                continue
            ts = self._parse_timestamp(ev.get("time_created"))
            if not ts or ts < hace_7:
                continue
            if ev.get("level") == 1:
                n_criticos += 1
            else:
                n_errores += 1
        if not n_criticos and not n_errores:
            return []
        return [Finding(
            severity="error" if n_criticos else "warning",
            collector_id="critical_events",
            message=(f"{n_criticos + n_errores} evento(s) críticos del sistema en los últimos 7 días"
                     + (f" ({n_criticos} críticos)" if n_criticos else "")),
            details={"criticos": n_criticos, "errores": n_errores},
        )]

    # ========== REGLAS DE SINTOMAS DE SOPORTE ==========

    def _check_disk_slow(self, observations: list[CollectorResult]) -> list[Finding]:
        """Disco lento: latencia por transferencia o disco saturado.

        Solo evalua discos con actividad; un disco inactivo no es "lento".
        """
        result = self._find_collector(observations, "disk_performance")
        if not result:
            return []
        findings = []
        for data in self._lista_dicts(self._get_data(result)):
            try:
                avg = float(data.get("avg_transfer_sec") or 0)
                pct = float(data.get("percent_disk_time") or 0)
                queue = float(data.get("current_disk_queue_length") or 0)
                ops = (float(data.get("read_ops_per_sec") or 0)
                       + float(data.get("write_ops_per_sec") or 0))
            except (TypeError, ValueError):
                continue
            if ops <= 0:
                continue
            disco = data.get("disk") or "disco"
            if avg >= 0.2:
                severidad = "error"
                motivo = f"latencia media de {avg * 1000:.0f} ms por transferencia"
            elif avg >= 0.05 and (pct >= 70 or queue >= 2):
                severidad = "warning"
                motivo = (f"latencia media de {avg * 1000:.0f} ms con "
                          f"{pct:.0f}% de tiempo ocupado")
            elif pct >= 90 and queue >= 4:
                severidad = "warning"
                motivo = f"disco saturado ({pct:.0f}% de tiempo, cola {queue:g})"
            else:
                continue
            findings.append(Finding(
                severity=severidad,
                collector_id="disk_performance",
                message=f"Disco lento: {disco} ({motivo})",
                details={"disk": disco, "avg_transfer_sec": avg,
                         "percent_disk_time": pct, "queue_length": queue,
                         "ops_per_sec": ops},
                knowledge_id="disco_lento",
            ))
        return findings

    def _check_process_high_cpu(self, observations: list[CollectorResult]) -> list[Finding]:
        """Proceso que consume una parte alta de la CPU total del equipo."""
        result = self._find_collector(observations, "top_processes")
        if not result:
            return []
        findings = []
        for data in self._lista_dicts(self._get_data(result)):
            valor = data.get("cpu_percent")
            if valor is None:
                continue
            try:
                cpu = float(valor)
            except (TypeError, ValueError):
                continue
            if cpu >= 70:
                severidad = "error"
            elif cpu >= 40:
                severidad = "warning"
            else:
                continue
            nombre = data.get("name") or "proceso"
            findings.append(Finding(
                severity=severidad,
                collector_id="top_processes",
                message=(f"Proceso con CPU alta: {nombre} "
                         f"(PID {data.get('pid')}, {cpu:.1f}% del total)"),
                details={"name": nombre, "pid": data.get("pid"),
                         "cpu_percent": cpu,
                         "cpu_percent_total": data.get("cpu_percent_total"),
                         "memory_mb": data.get("memory_mb")},
                knowledge_id="proceso_alto_cpu",
            ))
        return findings

    def _check_security_compromised(self, observations: list[CollectorResult]) -> list[Finding]:
        """Indicios de seguridad comprometida con evidencia de solo lectura.

        No afirma una intrusion: informa combinaciones objetivas (antivirus y
        firewall deshabilitados a la vez, intentos de inicio de sesion fallidos
        repetidos, firmas desactualizadas).
        """
        findings: list[Finding] = []

        av = self._find_collector(observations, "antivirus_status")
        firewall = self._find_collector(observations, "firewall_status")
        av_apagado = False
        if av:
            productos = self._lista_dicts(self._get_data(av))
            av_apagado = bool(productos) and not any(
                p.get("enabled") is True or p.get("real_time_protection") is True
                for p in productos)
        fw_apagado = False
        if firewall:
            perfiles = self._lista_dicts(self._get_data(firewall))
            fw_apagado = bool(perfiles) and not any(
                p.get("enabled") is True for p in perfiles)

        if av_apagado and fw_apagado:
            findings.append(Finding(
                severity="critical",
                collector_id="antivirus_status",
                message=("Indicios de seguridad comprometida: antivirus y "
                         "firewall deshabilitados al mismo tiempo"),
                details={"antivirus_habilitado": False,
                         "firewall_habilitado": False},
                knowledge_id="seguridad_comprometida",
            ))

        eventos = self._find_collector(observations, "security_events")
        if eventos:
            fallidos = 0
            for ev in self._lista_dicts(self._get_data(eventos)):
                if ev.get("id") == 4625:
                    fallidos += 1
            if fallidos >= 5:
                findings.append(Finding(
                    severity="error" if fallidos >= 10 else "warning",
                    collector_id="security_events",
                    message=(f"{fallidos} inicio(s) de sesion fallidos en los "
                             "ultimos eventos de seguridad"),
                    details={"failed_logons": fallidos},
                    knowledge_id="seguridad_comprometida",
                ))

        centro = self._find_collector(observations, "security_center")
        if centro:
            desactualizados = [
                p.get("display_name") or p.get("type") or "producto"
                for p in self._lista_dicts(self._get_data(centro))
                if p.get("up_to_date") is False]
            if desactualizados:
                findings.append(Finding(
                    severity="warning",
                    collector_id="security_center",
                    message=("Firmas de seguridad desactualizadas: "
                             + ", ".join(str(x) for x in desactualizados)),
                    details={"products": desactualizados},
                    knowledge_id="seguridad_comprometida",
                ))
        return findings

    def _check_service_wont_start(self, observations: list[CollectorResult]) -> list[Finding]:
        """Servicio automatico que no arranca o que falla con codigo de salida."""
        findings: list[Finding] = []
        vistos: set[tuple] = set()
        for collector_id in ("critical_services", "service_failures"):
            result = self._find_collector(observations, collector_id)
            if not result:
                continue
            for svc in self._extract_services(self._get_data(result)):
                start_mode = (svc.get("start_mode") or "").lower()
                state = (svc.get("state") or "").lower()
                if start_mode != "auto" or state == "running":
                    continue
                nombre = svc.get("display_name") or svc.get("name") or "desconocido"
                clave = (collector_id, nombre, state)
                if clave in vistos:
                    continue
                vistos.add(clave)
                exit_code = svc.get("exit_code")
                detalle = f"estado: {svc.get('state') or 'desconocido'}"
                if exit_code not in (None, 0, "0"):
                    detalle += f", codigo de salida: {exit_code}"
                findings.append(Finding(
                    severity="error",
                    collector_id=collector_id,
                    message=f"Servicio no inicia: {nombre} ({detalle})",
                    details={"name": svc.get("name"),
                             "display_name": svc.get("display_name"),
                             "state": svc.get("state"),
                             "start_mode": svc.get("start_mode"),
                             "exit_code": exit_code},
                    knowledge_id="servicio_no_inicia",
                ))
        return findings


    # ========== REGLAS DE RED, PUERTOS Y PERIFERICOS ==========

    def _check_exposed_ports(self, observations: list[CollectorResult]) -> list[Finding]:
        """Procesos de terceros que escuchan en todas las interfaces."""
        result = self._find_collector(observations, "listening_ports")
        if not result:
            return []
        data = self._primer_dict(self._get_data(result))
        if not data:
            return []
        expuestos = self._lista_dicts(data.get("third_party_exposed"))
        if not expuestos:
            return []
        # El mismo proceso puede escuchar en IPv4 (0.0.0.0) e IPv6 (::) para el
        # mismo puerto: se informa una vez por proceso y puerto.
        unicos: dict[tuple[str, Any], dict] = {}
        for item in expuestos:
            clave = (str(item.get("process_name") or ""), item.get("local_port"))
            actual = unicos.get(clave)
            if actual is None:
                unicos[clave] = item
            elif item.get("protocol") == "tcp" and actual.get("protocol") != "tcp":
                unicos[clave] = item
        muestras = []
        for item in list(unicos.values())[:10]:
            nombre = item.get("process_name") or "(sin nombre)"
            muestras.append(f"{nombre}:{item.get('local_port')}")
        return [Finding(
            severity="warning",
            collector_id="listening_ports",
            message=(f"{len(unicos)} puerto(s) de procesos de terceros "
                     "escuchan en todas las interfaces"),
            details={"total": len(unicos),
                     "listeners": len(expuestos),
                     "muestra": muestras,
                     "puertos": [item.get("local_port")
                                 for item in unicos.values()]},
            knowledge_id="puerto_expuesto",
        )]

    def _check_lan_visibility(self, observations: list[CollectorResult]) -> list[Finding]:
        """Puerta de enlace sin respuesta o red local sin otros equipos visibles."""
        alcanzabilidad = self._find_collector(observations, "lan_reachability")
        data = self._primer_dict(self._get_data(alcanzabilidad)) if alcanzabilidad else None
        if not data:
            return []

        if data.get("gateway_reachable") is False:
            return [Finding(
                severity="error",
                collector_id="lan_reachability",
                message=(f"La puerta de enlace {data.get('gateway_ip') or 'predeterminada'} "
                         "no respondio"),
                details={"gateway_ip": data.get("gateway_ip"),
                         "gateway_status": data.get("gateway_status"),
                         "checked_count": data.get("checked_count")},
                knowledge_id="equipos_red_no_visibles",
            )]

        comprobados = data.get("checked_count")
        alcanzables = data.get("reachable_count")
        try:
            comprobados_n = int(comprobados or 0)
            alcanzables_n = int(alcanzables or 0)
        except (TypeError, ValueError):
            comprobados_n = alcanzables_n = 0

        if comprobados_n > 0 and alcanzables_n == 0:
            return [Finding(
                severity="warning",
                collector_id="lan_reachability",
                message=(f"Ninguno de los {comprobados_n} equipo(s) conocido(s) "
                         "respondio a ping (pueden bloquear ICMP)"),
                details={"checked_count": comprobados_n,
                         "reachable_count": 0},
                knowledge_id="equipos_red_no_visibles",
            )]

        vecinos = self._find_collector(observations, "network_neighbors")
        ndata = self._primer_dict(self._get_data(vecinos)) if vecinos else None
        if ndata:
            try:
                otros = int(ndata.get("other_host_count") or 0)
            except (TypeError, ValueError):
                otros = 0
            if otros == 0:
                return [Finding(
                    severity="warning",
                    collector_id="network_neighbors",
                    message="No se ven otros equipos en la red local (puede ser una red aislada)",
                    details={"neighbor_count": ndata.get("neighbor_count"),
                             "visible_count": ndata.get("visible_count")},
                    knowledge_id="equipos_red_no_visibles",
                )]
        return []

    def _check_suspicious_traffic(self, observations: list[CollectorResult]) -> list[Finding]:
        """Configuracion que puede desviar el trafico, sin afirmar una intrusion."""
        proxy = self._primer_dict(
            self._get_data(self._find_collector(observations, "proxy_settings")))
        hosts = self._primer_dict(
            self._get_data(self._find_collector(observations, "hosts_entries")))
        captura = self._primer_dict(
            self._get_data(self._find_collector(observations, "capture_drivers")))
        if not proxy and not hosts and not captura:
            return []

        anomalias = []
        hosts_no_loopback = 0
        if hosts:
            try:
                hosts_no_loopback = int(hosts.get("non_loopback_count") or 0)
            except (TypeError, ValueError):
                hosts_no_loopback = 0
            if hosts_no_loopback:
                anomalias.append(f"{hosts_no_loopback} entrada(s) activas en hosts "
                                 "fuera de loopback")
        manual_remoto = bool(proxy and proxy.get("manual_remote_proxy") is True)
        if manual_remoto:
            anomalias.append(f"proxy manual remoto: {proxy.get('user_proxy_server')}")
        entorno = 0
        if proxy:
            try:
                entorno = int(proxy.get("environment_proxy_count") or 0)
            except (TypeError, ValueError):
                entorno = 0
            if entorno:
                anomalias.append(f"{entorno} variable(s) de proxy en el entorno")
        if not anomalias:
            return []

        en_ejecucion = 0
        if captura:
            try:
                en_ejecucion = int(captura.get("running_count") or 0)
            except (TypeError, ValueError):
                en_ejecucion = 0
        combinado = en_ejecucion > 0 and (hosts_no_loopback > 0 or manual_remoto)
        return [Finding(
            severity="error" if combinado else "warning",
            collector_id="proxy_settings",
            message="Configuracion que puede desviar el trafico: " + "; ".join(anomalias),
            details={"hosts_non_loopback": hosts_no_loopback,
                     "manual_remote_proxy": manual_remoto,
                     "environment_proxy_count": entorno,
                     "proxy_server": (proxy or {}).get("user_proxy_server", ""),
                     "capture_drivers_running": en_ejecucion,
                     "capture_present": bool(captura and captura.get("present"))},
            knowledge_id="trafico_red_alterado",
        )]

    def _check_gateway_unreachable(self, observations: list[CollectorResult]) -> list[Finding]:
        """Ruta predeterminada ausente o puerta de enlace sin respuesta."""
        result = self._find_collector(observations, "gateway_routes")
        if not result:
            return []
        data = self._primer_dict(self._get_data(result))
        if not data:
            return []
        try:
            total = int(data.get("gateway_count") or 0)
        except (TypeError, ValueError):
            total = 0
        if total == 0:
            return [Finding(
                severity="warning",
                collector_id="gateway_routes",
                message="No hay una ruta predeterminada configurada",
                details={"gateway_count": 0},
                knowledge_id="gateway_no_responde",
            )]
        puerta = data.get("primary_gateway") or ""
        if puerta and data.get("primary_reachable") is False:
            return [Finding(
                severity="error",
                collector_id="gateway_routes",
                message=f"La puerta de enlace {puerta} no respondio a ping",
                details={"gateway": puerta,
                         "reachable_count": data.get("reachable_count"),
                         "gateway_count": total,
                         "interface_index": data.get("primary_interface_index")},
                knowledge_id="gateway_no_responde",
            )]
        return []

    def _check_dns_instability(self, observations: list[CollectorResult]) -> list[Finding]:
        """Resolucion DNS fallida o lenta con los servidores configurados."""
        servidores = self._primer_dict(
            self._get_data(self._find_collector(observations, "gateway_dns_servers")))
        if servidores:
            try:
                unicos = int(servidores.get("unique_count") or 0)
            except (TypeError, ValueError):
                unicos = 0
            if unicos == 0:
                return [Finding(
                    severity="warning",
                    collector_id="gateway_dns_servers",
                    message="No hay servidores DNS configurados",
                    details={"interface_count": servidores.get("interface_count")},
                    knowledge_id="dns_inestable",
                )]

        result = self._find_collector(observations, "dns_resolution")
        if not result:
            return []
        data = self._primer_dict(self._get_data(result))
        if not data:
            return []
        nombre = data.get("query_name") or "el nombre de prueba"
        if data.get("success") is False:
            motivo = ("tiempo de espera agotado" if data.get("timed_out")
                      else (data.get("error") or "sin respuesta"))
            return [Finding(
                severity="error",
                collector_id="dns_resolution",
                message=f"La resolucion DNS fallo para {nombre} ({motivo})",
                details={"query_name": nombre,
                         "timed_out": bool(data.get("timed_out")),
                         "elapsed_ms": data.get("elapsed_ms")},
                knowledge_id="dns_inestable",
            )]
        try:
            transcurrido = int(data.get("elapsed_ms") or 0)
        except (TypeError, ValueError):
            transcurrido = 0
        if data.get("success") is True and transcurrido >= 1500:
            return [Finding(
                severity="warning",
                collector_id="dns_resolution",
                message=f"La resolucion DNS tardo {transcurrido} ms para {nombre}",
                details={"query_name": nombre, "elapsed_ms": transcurrido},
                knowledge_id="dns_inestable",
            )]
        return []

    def _check_input_device(self, observations: list[CollectorResult],
                            clave: str, clave_pnp: str, etiqueta: str,
                            knowledge_id: str) -> list[Finding]:
        """Dispositivo de entrada con error o ninguno detectado."""
        result = self._find_collector(observations, "input_devices")
        if not result:
            return []
        data = self._primer_dict(self._get_data(result))
        if not data:
            return []
        vistos: set[str] = set()
        problemas = []
        for campo in (clave, clave_pnp):
            for item in self._lista_dicts(data.get(campo)):
                nombre = str(item.get("name") or etiqueta)
                identificador = str(item.get("pnp_device_id") or nombre)
                if identificador in vistos:
                    continue
                vistos.add(identificador)
                try:
                    codigo = int(item.get("config_manager_error_code") or 0)
                except (TypeError, ValueError):
                    codigo = 0
                estado = str(item.get("status") or "").strip()
                if codigo != 0 or (estado and estado.upper() not in ("OK", "UNKNOWN")):
                    problemas.append({
                        "name": nombre,
                        "status": estado,
                        "config_manager_error_code": codigo,
                    })
        if problemas:
            primero = problemas[0]
            detalle = f"estado: {primero['status'] or 'desconocido'}"
            if primero["config_manager_error_code"]:
                detalle += f", codigo: {primero['config_manager_error_code']}"
            return [Finding(
                severity="error",
                collector_id="input_devices",
                message=f"{etiqueta.capitalize()} con problemas: {primero['name']} ({detalle})",
                details={"devices": problemas, "total": len(problemas)},
                knowledge_id=knowledge_id,
            )]
        if not vistos:
            return [Finding(
                severity="warning",
                collector_id="input_devices",
                message=f"No se detectaron {etiqueta}",
                details={"detected": 0},
                knowledge_id=knowledge_id,
            )]
        return []

    def _check_keyboard(self, observations: list[CollectorResult]) -> list[Finding]:
        """Teclados detectados con error de configuracion."""
        return self._check_input_device(
            observations, "keyboards", "pnp_keyboards", "teclados",
            "teclado_no_responde")

    def _check_pointing_device(self, observations: list[CollectorResult]) -> list[Finding]:
        """Dispositivos de puntero detectados con error de configuracion."""
        return self._check_input_device(
            observations, "pointing_devices", "pnp_pointing_devices",
            "dispositivos de puntero", "mouse_no_responde")


# Instancia global del motor de reglas
_engine = RuleEngine()


# Estados de colector que NO son un resultado valido: el colector no se pudo
# evaluar (permisos, no disponible, error o tiempo agotado). Nunca deben
# interpretarse como "sin problemas".
_ESTADOS_NO_EVALUADO = {
    "denied": "No evaluado (requiere administrador)",
    "not_available": "No evaluado (no disponible en este equipo)",
    "error": "No evaluado (error al recopilar)",
    "timeout": "No evaluado (tiempo de espera agotado)",
}


def _estado_observacion(obs) -> str:
    """Status de un CollectorResult (tolerando query dict u objeto)."""
    query = getattr(obs, "query", None)
    if isinstance(query, dict):
        return query.get("status", "")
    return getattr(query, "status", "") if query else ""


def _findings_no_evaluados(observations: list[CollectorResult]) -> list[Finding]:
    """Findings sinteticos para colectores que no se pudieron evaluar."""
    findings: list[Finding] = []
    for obs in observations:
        status = _estado_observacion(obs)
        mensaje = _ESTADOS_NO_EVALUADO.get(status)
        if not mensaje:
            continue
        findings.append(Finding(
            severity="warning",
            collector_id=getattr(obs, "collector_id", ""),
            message=mensaje,
            details={"no_evaluado": True, "requiere_admin": status == "denied",
                     "status": status},
        ))
    return findings


def _collector_datos_limitados(obs) -> bool:
    """True si el colector termino en ok pero declara datos parciales.

    Los colectores que sin permisos solo leen parte de la informacion lo
    declaran en sus datos (por ejemplo ``optional_features_available``). Los
    datos llegan como lista de diccionarios.
    """
    if _estado_observacion(obs) != "ok":
        return False
    data = getattr(obs, "data", None)
    if isinstance(data, dict):
        return data.get("optional_features_available") is False
    if isinstance(data, list):
        for x in data:
            if isinstance(x, dict):
                return x.get("optional_features_available") is False
    return False


def _findings_datos_limitados(observations: list[CollectorResult]) -> list[Finding]:
    """Avisos para colectores con datos parciales por falta de permisos."""
    findings: list[Finding] = []
    vistos: set[str] = set()
    for obs in observations:
        cid = getattr(obs, "collector_id", "")
        if cid in vistos or not _collector_datos_limitados(obs):
            continue
        vistos.add(cid)
        findings.append(Finding(
            severity="warning",
            collector_id=cid,
            message="Datos limitados (requiere administrador)",
            details={"datos_limitados": True, "requiere_admin": True},
        ))
    return findings


def diagnose(symptom: str, observations: list[CollectorResult]) -> DiagnosticResult:
    """Ejecuta el diagnostico para un sintoma dado."""
    findings = _engine.evaluate(symptom, observations)
    kb.attach_knowledge(findings)
    findings = _agrupar_findings(findings)
    findings.extend(_findings_no_evaluados(observations))
    findings.extend(_findings_datos_limitados(observations))
    recommendations = _generate_recommendations(findings)
    return DiagnosticResult(
        symptom=symptom,
        findings=findings,
        recommendations=recommendations
    )


def diagnose_symptoms(symptoms: list[str], observations: list[CollectorResult]) -> tuple[list[Finding], list[str]]:
    """Evalua todas las reglas de una lista de sintomas, sin duplicar hallazgos."""
    findings: list[Finding] = []
    seen: set[tuple] = set()
    for symptom in symptoms:
        for f in _engine.evaluate(symptom, observations):
            key = (f.severity, f.collector_id, f.message)
            if key not in seen:
                seen.add(key)
                findings.append(f)
    severity_order = {"critical": 0, "error": 1, "warning": 2, "ok": 3}
    findings.sort(key=lambda f: severity_order.get(f.severity, 9))
    kb.attach_knowledge(findings)
    findings = _agrupar_findings(findings)
    findings.extend(_findings_no_evaluados(observations))
    findings.extend(_findings_datos_limitados(observations))
    return findings, _generate_recommendations(findings)


def _agrupar_findings(findings: list[Finding]) -> list[Finding]:
    """Une los findings repetidos del mismo problema en una sola entrada.

    Dos findings se consideran el mismo problema si comparten entrada de
    conocimiento (o colector) y severidad. El primer finding del grupo
    conserva el mensaje principal y recibe en ``details``:
    - ``grupo_total``: cantidad de ocurrencias
    - ``grupo_mensajes``: lista con todos los mensajes (incluye el propio)
    """
    grupos: dict[tuple, dict] = {}
    orden: list[dict] = []
    for f in findings:
        clave = (f.knowledge_id or f.collector_id, f.severity)
        g = grupos.get(clave)
        if g is None:
            g = {"base": f, "mensajes": [f.message]}
            grupos[clave] = g
            orden.append(g)
        else:
            g["mensajes"].append(f.message)
    salida: list[Finding] = []
    for g in orden:
        f = g["base"]
        if len(g["mensajes"]) > 1:
            f.details = dict(f.details or {})
            f.details["grupo_total"] = len(g["mensajes"])
            f.details["grupo_mensajes"] = list(g["mensajes"])
        salida.append(f)
    return salida


def _generate_recommendations(findings: list[Finding]) -> list[str]:
    """Genera recomendaciones basadas en los hallazgos."""
    recommendations = []
    critical = sum(1 for f in findings if f.severity == "critical")
    error = sum(1 for f in findings if f.severity == "error")
    warning = sum(1 for f in findings if f.severity == "warning")

    if critical > 0:
        recommendations.append("Problema crítico detectado. Requiere atención inmediata.")
    if error > 0:
        recommendations.append("Errores detectados. Revise la configuración.")
    if warning > 0:
        recommendations.append("Advertencias detectadas. Monitoree la situación.")
    if not findings:
        recommendations.append("No se detectaron problemas obvios.")

    return recommendations
