# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Motor de reglas de diagnostico para DiagUSB."""

from datetime import datetime, timedelta, timezone
from typing import Any

from .models import CollectorResult, DiagnosticResult, Finding
from .context_aware import SystemContext, detect_context_from_observations, get_context_aware_rules
from . import knowledge_base as kb


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
        self.register("no_hay_internet", self._check_network_adapter_enabled)
        self.register("no_hay_internet", self._check_gateway_reachable)
        self.register("no_hay_internet", self._check_internet_connectivity)
        self.register("red_lenta", self._check_network_speed)
        self.register("dns_no_responde", self._check_dns_config)

        # ========== REGLAS DE DISCO ==========
        self.register("disco_lleno", self._check_disk_space)
        self.register("disco_salud", self._check_disk_health)

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
        data = self._get_data(result)
        if isinstance(data, dict):
            spooler = data.get("spooler", {})
            if isinstance(spooler, dict) and spooler.get("state") != "Running":
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
        available_drivers = {d.get("name", "").lower() for d in drivers}
        for printer in printers:
            driver = printer.get("driver_name", "")
            if driver and driver.lower() not in available_drivers:
                findings.append(Finding(
                    severity="critical",
                    collector_id="printers",
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
            if printer.get("detected_error_state", 0) != 0:
                findings.append(Finding(
                    severity="error",
                    collector_id="printers",
                    message="Estado de error detectado en impresora",
                    details={"printer": printer.get("name", ""), "error_state": printer.get("detected_error_state")}
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
        """Verifica que los adaptadores de red esten habilitados."""
        result = self._find_collector(observations, "network_adapters")
        if not result:
            return []
        findings = []
        adapters = self._get_data(result) if isinstance(self._get_data(result), list) else []
        enabled_adapters = [a for a in adapters if a.get("status") == "Up"]
        if not enabled_adapters:
            findings.append(Finding(
                severity="critical",
                collector_id="network_adapters",
                message="No hay adaptadores de red habilitados",
                details={"total_adapters": len(adapters), "enabled": 0}
            ))
        return findings

    def _check_gateway_reachable(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica que el gateway sea alcanzable."""
        result = self._find_collector(observations, "connectivity")
        if not result:
            return []
        findings = []
        data = self._get_data(result)
        if isinstance(data, dict):
            gateway = data.get("gateway_ping", {})
            if gateway.get("reachable") is False:
                findings.append(Finding(
                    severity="error",
                    collector_id="connectivity",
                    message="El gateway no es alcanzable",
                    details={"gateway": gateway.get("address"), "latency": gateway.get("latency")}
                ))
        return findings

    def _check_internet_connectivity(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica conectividad a internet."""
        result = self._find_collector(observations, "connectivity")
        if not result:
            return []
        findings = []
        data = self._get_data(result)
        if isinstance(data, dict):
            internet = data.get("internet_test", {})
            if internet.get("reachable") is False:
                findings.append(Finding(
                    severity="critical",
                    collector_id="connectivity",
                    message="No hay conectividad a internet",
                    details={"target": internet.get("target")}
                ))
        return findings

    def _check_network_speed(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica velocidad del adaptador de red."""
        result = self._find_collector(observations, "network_adapters")
        if not result:
            return []
        findings = []
        adapters = self._get_data(result) if isinstance(self._get_data(result), list) else []
        for adapter in adapters:
            speed = adapter.get("speed", 0)
            if speed and speed < 100_000_000:  # Menos de 100 Mbps
                findings.append(Finding(
                    severity="warning",
                    collector_id="network_adapters",
                    message=f"Adaptador de red con velocidad baja: {speed // 1_000_000} Mbps",
                    details={"adapter": adapter.get("name"), "speed": speed}
                ))
        return findings

    def _check_dns_config(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica configuracion de DNS."""
        result = self._find_collector(observations, "dns_servers")
        if not result:
            return []
        findings = []
        data = self._get_data(result)
        if isinstance(data, dict):
            dns = data.get("dns_servers", [])
            if not dns:
                findings.append(Finding(
                    severity="error",
                    collector_id="dns_servers",
                    message="No hay servidores DNS configurados",
                    details={}
                ))
        return findings

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
        findings = []
        data = self._get_data(result)
        if isinstance(data, dict):
            if not data.get("antivirus_enabled"):
                findings.append(Finding(
                    severity="critical",
                    collector_id="antivirus_status",
                    message="Antivirus deshabilitado",
                    details={"product": data.get("antivirus_product")}
                ))
        return findings

    def _check_firewall_enabled(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica que el firewall este habilitado."""
        result = self._find_collector(observations, "firewall_status")
        if not result:
            return []
        findings = []
        data = self._get_data(result)
        if isinstance(data, dict):
            profiles = data.get("profiles", {})
            enabled_count = sum(1 for p in profiles.values() if p.get("enabled"))
            if enabled_count == 0:
                findings.append(Finding(
                    severity="error",
                    collector_id="firewall_status",
                    message="Todos los perfiles de firewall están deshabilitados",
                    details={"enabled_profiles": enabled_count}
                ))
        return findings

    # ========== REGLAS DE MEMORIA ==========

    def _check_memory_usage(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica uso de memoria."""
        result = self._find_collector(observations, "memory_status")
        if not result:
            return []
        findings = []
        data = self._get_data(result)
        if isinstance(data, dict):
            usage_percent = data.get("memory_usage_percent", 0)
            if usage_percent > 95:
                findings.append(Finding(
                    severity="critical",
                    collector_id="memory_status",
                    message=f"Memoria casi llena: {usage_percent:.1f}% en uso",
                    details={"usage_percent": usage_percent}
                ))
            elif usage_percent > 85:
                findings.append(Finding(
                    severity="warning",
                    collector_id="memory_status",
                    message=f"Memoria alta: {usage_percent:.1f}% en uso",
                    details={"usage_percent": usage_percent}
                ))
        return findings

    def _check_high_cpu_usage(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica uso alto de CPU."""
        result = self._find_collector(observations, "system_performance")
        if not result:
            return []
        findings = []
        data = self._get_data(result)
        if isinstance(data, dict):
            cpu_usage = data.get("cpu_load_percent", 0)
            if cpu_usage > 90:
                findings.append(Finding(
                    severity="warning",
                    collector_id="system_performance",
                    message=f"Uso alto de CPU: {cpu_usage:.1f}%",
                    details={"cpu_usage": cpu_usage}
                ))
        return findings

    def _check_disk_queue(self, observations: list[CollectorResult]) -> list[Finding]:
        """Verifica cola de disco."""
        result = self._find_collector(observations, "disk_performance")
        if not result:
            return []
        findings = []
        data = self._get_data(result)
        if isinstance(data, dict):
            queue = data.get("current_disk_queue_length", 0)
            if queue > 10:
                findings.append(Finding(
                    severity="warning",
                    collector_id="disk_performance",
                    message=f"Cola de disco alta: {queue}",
                    details={"queue_length": queue}
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
        data = self._get_data(result)
        if not isinstance(data, list):
            return []
        debiles = []
        for red in data:
            if not isinstance(red, dict):
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
