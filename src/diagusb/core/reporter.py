# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 Daniel Ricardo Novoa
"""Reporters para DiagUSB."""

from datetime import datetime
from pathlib import Path
from typing import Optional

from .models import DiagnosticResult, Finding, ContextResult
from .informe import SEVERIDAD_LABEL, _primer_dict


_ESTADOS_NO_EVALUADO = ("denied", "not_available", "error", "timeout")


def _status_de(result) -> str:
    """Status de un CollectorResult (tolerando query dict u objeto)."""
    query = getattr(result, "query", None)
    if isinstance(query, dict):
        return query.get("status", "")
    return getattr(query, "status", "") if query else ""


def _datos_limitados(diagnostic: DiagnosticResult) -> list[str]:
    """Colectores con datos parciales por permisos, como 'id (razon)'."""
    limite = []
    for c in (diagnostic.collector_results or []):
        if getattr(c, "collector_id", "") != "installed_software":
            continue
        if _status_de(c) != "ok":
            continue
        data = _primer_dict(getattr(c, "data", None))
        if data is not None and data.get("optional_features_available") is False:
            limite.append("installed_software (requiere administrador)")
    return limite


def _linea_alcance(diagnostic: DiagnosticResult) -> str:
    """Linea 'Alcance: ...' con el modo, no evaluados y datos limitados."""
    ctx = getattr(diagnostic, "context", None)
    modo = "administrador" if (ctx and getattr(ctx, "is_elevated", False)) else "estándar"
    no_eval = [getattr(c, "collector_id", "") for c in (diagnostic.collector_results or [])
               if _status_de(c) in _ESTADOS_NO_EVALUADO]
    lista = ", ".join([x for x in no_eval if x]) or "ninguno"
    linea = f"Alcance: modo {modo}; no evaluados: {lista}"
    lim = _datos_limitados(diagnostic)
    if lim:
        linea += "; datos limitados: " + ", ".join(lim)
    return linea


class ConsoleReporter:
    """Reporter para consola con colores ANSI."""

    COLORS = {
        "reset": "\033[0m",
        "ok": "\033[92m",       # Verde
        "warning": "\033[93m",  # Amarillo
        "error": "\033[91m",    # Rojo
        "critical": "\033[95m", # Magenta
        "info": "\033[96m",     # Cyan
        "bold": "\033[1m",
    }

    EMOJIS = {
        "ok": "\u2705",       # ✓
        "warning": "\u26A0\uFE0F",  # ⚠
        "error": "\u274C",    # ✗
        "critical": "\u2757", # ❗
        "info": "\u2139\uFE0F", # ℹ
    }

    def render(self, diagnostic: DiagnosticResult, use_emoji: bool = True) -> str:
        """
        Renderiza el diagnostico en formato de consola.

        Args:
            diagnostic: Resultado del diagnostico.
            use_emoji: Si usar emojis en la salida.

        Returns:
            Cadena formateada para la consola.
        """
        lines = []
        lines.append("")
        lines.append(self._colorize(f"{self._bold('=== DIAGNOSTICO: ' + diagnostic.symptom + ' ===')}", "bold"))
        lines.append("")

        # Informacion de contexto
        if diagnostic.context:
            ctx = diagnostic.context
            lines.append(self._colorize("CONTEXTO:", "info"))
            if ctx.computer_name:
                lines.append(f"  Computadora: {ctx.computer_name}")
            if ctx.user:
                lines.append(f"  Usuario: {ctx.user}")
            if ctx.is_elevated:
                lines.append(f"  Elevado: {self._colorize('Sí', 'warning')}")
            else:
                lines.append(f"  Elevado: No")
            lines.append(f"  {_linea_alcance(diagnostic)}")
            lines.append("")

        # Informacion de contexto del sistema (notebook/desktop/server)
        if diagnostic.system_context:
            sc = diagnostic.system_context
            lines.append(self._colorize("CONTEXTO DEL SISTEMA:", "info"))
            type_icon = ""
            if sc.system_type == "server":
                type_icon = " \U0001F5A5"  # Servidor
            elif sc.system_type == "notebook":
                type_icon = " \U0001F4BB"  # Laptop
            elif sc.system_type == "desktop":
                type_icon = " \U0001F5A5"  # PC
            lines.append(f"  Tipo de sistema: {sc.system_type}{type_icon}")
            lines.append(f"  Factor de forma: {sc.form_factor}")
            if sc.manufacturer:
                lines.append(f"  Fabricante: {sc.manufacturer}")
            if sc.model:
                lines.append(f"  Modelo: {sc.model}")
            if sc.processor_family:
                lines.append(f"  Procesador: {sc.processor_family}")
            lines.append(f"  Memoria RAM: {sc.total_memory_gb} GB")
            if sc.domain:
                lines.append(f"  Dominio: {sc.domain}")
            lines.append(f"  Sistema operativo: {sc.os_type}")
            lines.append(f"  Version SO: {sc.os_version}")
            lines.append(f"  Uptime: {sc.uptime_hours} horas")
            lines.append(f"  Virtual: {'Sí' if sc.is_virtual else 'No'}")
            lines.append(f"  Batería: {'Sí' if sc.has_battery else 'No'}")
            lines.append(f"  WiFi: {'Sí' if sc.has_wifi else 'No'}")
            lines.append("")

        # Timestamps de colectores
        if diagnostic.collector_results:
            lines.append(self._colorize("COLECTORES:", "info"))
            for cr in diagnostic.collector_results:
                timestamp = cr.captured_at_utc or "N/A"
                duration = f"{cr.query.duration_ms}ms" if cr.query.duration_ms else "N/A"
                status_icon = self._emoji(cr.query.status, use_emoji) if cr.query.status else ""
                lines.append(f"  {status_icon} [{cr.collector_id}] {timestamp} ({duration})")
            lines.append("")

        # Hallazgos
        if not diagnostic.findings:
            lines.append(self._colorize(f"{self._emoji('ok', use_emoji)} No se encontraron problemas.", "ok"))
        else:
            for finding in diagnostic.findings:
                severity_label = SEVERIDAD_LABEL.get(finding.severity, finding.severity.upper())
                color = self._get_severity_color(finding.severity)
                emoji = self._emoji(finding.severity, use_emoji)
                lines.append(self._colorize(f"{emoji} [{severity_label}] {finding.message}", color))
                if finding.details:
                    for key, value in finding.details.items():
                        lines.append(f"   {key}: {value}")

        # Resumen con contadores
        summary = self.generate_summary(diagnostic)
        lines.append("")
        lines.append(self._colorize(self._bold("RESUMEN:"), "info"))
        lines.append(f"  Total de hallazgos: {summary['total_collectors']}")
        if summary['critical_count'] > 0:
            lines.append(f"  {self._colorize('Críticos: ' + str(summary['critical_count']), 'critical')}")
        if summary['error_count'] > 0:
            lines.append(f"  {self._colorize('Errores: ' + str(summary['error_count']), 'error')}")
        if summary['warning_count'] > 0:
            lines.append(f"  {self._colorize('Advertencias: ' + str(summary['warning_count']), 'warning')}")
        if summary['ok_count'] > 0:
            lines.append(f"  {self._colorize('OK: ' + str(summary['ok_count']), 'ok')}")

        if diagnostic.recommendations:
            lines.append("")
            lines.append(self._colorize(self._bold("RECOMENDACIONES:"), "info"))
            for rec in diagnostic.recommendations:
                lines.append(f"  -> {rec}")

        lines.append("")
        return "\n".join(lines)

    def generate_summary(self, diagnostic: DiagnosticResult) -> dict:
        """
        Genera un resumen del diagnostico.

        Args:
            diagnostic: Resultado del diagnostico.

        Returns:
            Diccionario con contadores de severidad.
        """
        counters = {
            "total_collectors": len(diagnostic.findings),
            "collectors_by_status": {},
            "critical_count": 0,
            "error_count": 0,
            "warning_count": 0,
            "ok_count": 0,
        }

        for finding in diagnostic.findings:
            severity = finding.severity
            counters["collectors_by_status"][severity] = counters["collectors_by_status"].get(severity, 0) + 1

            if severity == "critical":
                counters["critical_count"] += 1
            elif severity == "error":
                counters["error_count"] += 1
            elif severity == "warning":
                counters["warning_count"] += 1
            elif severity == "ok":
                counters["ok_count"] += 1

        return counters

    def _colorize(self, text: str, color: str) -> str:
        """Aplica color ANSI al texto."""
        color_code = self.COLORS.get(color, self.COLORS["reset"])
        return f"{color_code}{text}{self.COLORS['reset']}"

    def _bold(self, text: str) -> str:
        """Aplica negrita al texto."""
        return f"{self.COLORS['bold']}{text}{self.COLORS['reset']}"

    def _emoji(self, severity: str, use_emoji: bool) -> str:
        """Obtiene el emoji para la severidad."""
        if not use_emoji:
            return ""
        return self.EMOJIS.get(severity, "")

    def _get_severity_color(self, severity: str) -> str:
        """Obtiene el color para la severidad."""
        return {
            "ok": "ok",
            "warning": "warning",
            "error": "error",
            "critical": "critical",
        }.get(severity, "info")


class HtmlReporter:
    """Reporter HTML autocontenido."""

    CSS = """
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; color: #333; }
        .container { max-width: 900px; margin: 20px auto; background: #fff; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); overflow: hidden; }
        .header { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; padding: 20px 30px; }
        .header h1 { font-size: 1.5em; margin-bottom: 5px; }
        .header .subtitle { opacity: 0.9; font-size: 0.9em; }
        .content { padding: 20px 30px; }
        .symptom { font-size: 1.2em; color: #555; margin-bottom: 20px; padding-bottom: 10px; border-bottom: 2px solid #667eea; }
        .context { background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 20px; border: 1px solid #e9ecef; }
        .context h3 { color: #495057; margin-bottom: 10px; font-size: 1em; display: flex; align-items: center; gap: 8px; }
        .context-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 10px; }
        .context-item { display: flex; flex-direction: column; }
        .context-label { font-size: 0.8em; color: #6c757d; text-transform: uppercase; }
        .context-value { font-weight: 500; color: #212529; }
        .context-value.elevated { color: #d9534f; }
        .findings { margin-bottom: 20px; }
        .finding { padding: 15px; margin-bottom: 10px; border-radius: 6px; border-left: 4px solid; }
        .finding.critical { background: #ffe6e6; border-color: #d32f2f; }
        .finding.error { background: #fff3e0; border-color: #f57c00; }
        .finding.warning { background: #fffde7; border-color: #fbc02d; }
        .finding.ok { background: #e8f5e9; border-color: #388e3c; }
        .severity { font-weight: bold; text-transform: uppercase; font-size: 0.85em; padding: 3px 8px; border-radius: 3px; display: inline-block; margin-right: 10px; }
        .severity.critical { background: #d32f2f; color: white; }
        .severity.error { background: #f57c00; color: white; }
        .severity.warning { background: #fbc02d; color: #333; }
        .severity.ok { background: #388e3c; color: white; }
        .message { margin-top: 8px; font-size: 1.05em; }
        .details { margin-top: 8px; font-size: 0.9em; color: #666; font-family: monospace; }
        .details table { width: 100%; border-collapse: collapse; }
        .details td { padding: 4px 8px; border-bottom: 1px solid #eee; }
        .details td:first-child { font-weight: bold; width: 40%; }
        .collectors { background: #f8f9fa; border-radius: 6px; padding: 15px; margin-bottom: 20px; }
        .collectors h3 { color: #495057; margin-bottom: 10px; font-size: 1em; }
        .collector-table { width: 100%; border-collapse: collapse; font-size: 0.9em; }
        .collector-table th { text-align: left; padding: 8px; border-bottom: 2px solid #dee2e6; color: #495057; }
        .collector-table td { padding: 8px; border-bottom: 1px solid #dee2e6; }
        .collector-table tr:last-child td { border-bottom: none; }
        .summary { background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; border-radius: 6px; padding: 15px; margin-bottom: 20px; }
        .summary h3 { margin-bottom: 10px; font-size: 1em; }
        .summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(100px, 1fr)); gap: 10px; text-align: center; }
        .summary-item { background: rgba(255,255,255,0.2); border-radius: 4px; padding: 10px; }
        .summary-count { font-size: 1.5em; font-weight: bold; }
        .summary-label { font-size: 0.8em; opacity: 0.9; }
        .recommendations { background: #e3f2fd; padding: 15px; border-radius: 6px; margin-top: 20px; }
        .recommendations h3 { color: #1565c0; margin-bottom: 10px; }
        .recommendations ul { padding-left: 20px; }
        .recommendations li { margin-bottom: 5px; }
        .footer { background: #f5f5f5; padding: 15px 30px; text-align: center; font-size: 0.85em; color: #888; }
        .timestamp { color: #6c757d; font-size: 0.9em; }
    </style>
    """

    def render(self, diagnostic: DiagnosticResult, output_path: Optional[Path] = None) -> str:
        """
        Renderiza el diagnostico en HTML.

        Args:
            diagnostic: Resultado del diagnostico.
            output_path: Ruta donde guardar el HTML (opcional).

        Returns:
            Cadena HTML generada.
        """
        summary = self.generate_summary(diagnostic)
        generation_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        html_parts = [
            "<!DOCTYPE html>",
            "<html lang='es'>",
            "<head>",
            "<meta charset='UTF-8'>",
            "<meta name='viewport' content='width=device-width, initial-scale=1.0'>",
            "<title>DiagUSB - Diagnóstico</title>",
            self.CSS,
            "</head>",
            "<body>",
            "<div class='container'>",
            "<div class='header'>",
            "<h1>DiagUSB - Reporte de Diagnóstico</h1>",
            f"<div class='subtitle'>Generado: {generation_time}</div>",
            "</div>",
            "<div class='content'>",
            f"<div class='symptom'>Síntoma: {self._escape_html(diagnostic.symptom)}</div>",
        ]
        html_parts.append(f"<div class='subtitle'>{self._escape_html(_linea_alcance(diagnostic))}</div>")

        # Seccion de contexto
        if diagnostic.context:
            ctx = diagnostic.context
            html_parts.append("<div class='context'>")
            html_parts.append("<h3>\U0001F4BB Contexto del Sistema</h3>")
            html_parts.append("<div class='context-grid'>")
            if ctx.computer_name:
                html_parts.append(f"<div class='context-item'><span class='context-label'>Computadora</span><span class='context-value'>{self._escape_html(ctx.computer_name)}</span></div>")
            if ctx.user:
                html_parts.append(f"<div class='context-item'><span class='context-label'>Usuario</span><span class='context-value'>{self._escape_html(ctx.user)}</span></div>")
            html_parts.append(f"<div class='context-item'><span class='context-label'>Elevado</span><span class='context-value {'elevated' if ctx.is_elevated else ''}'>{'Sí' if ctx.is_elevated else 'No'}</span></div>")
            html_parts.append("</div></div>")

        # Seccion de contexto del sistema (notebook/desktop/server)
        if diagnostic.system_context:
            sc = diagnostic.system_context
            html_parts.append("<div class='context'>")
            html_parts.append("<h3>\U0001F5A5 Tipo de Equipo</h3>")
            html_parts.append("<div class='context-grid'>")
            type_emoji = "\U0001F5A5" if sc.system_type == "server" else ("\U0001F4BB" if sc.system_type == "notebook" else "\U0001F5A5")
            html_parts.append(f"<div class='context-item'><span class='context-label'>Tipo</span><span class='context-value'>{self._escape_html(sc.system_type)} {type_emoji}</span></div>")
            html_parts.append(f"<div class='context-item'><span class='context-label'>Factor Forma</span><span class='context-value'>{self._escape_html(sc.form_factor)}</span></div>")
            if sc.manufacturer:
                html_parts.append(f"<div class='context-item'><span class='context-label'>Fabricante</span><span class='context-value'>{self._escape_html(sc.manufacturer)}</span></div>")
            if sc.model:
                html_parts.append(f"<div class='context-item'><span class='context-label'>Modelo</span><span class='context-value'>{self._escape_html(sc.model)}</span></div>")
            if sc.processor_family:
                html_parts.append(f"<div class='context-item'><span class='context-label'>Procesador</span><span class='context-value'>{self._escape_html(sc.processor_family)}</span></div>")
            html_parts.append(f"<div class='context-item'><span class='context-label'>Memoria RAM</span><span class='context-value'>{sc.total_memory_gb} GB</span></div>")
            if sc.domain:
                html_parts.append(f"<div class='context-item'><span class='context-label'>Dominio</span><span class='context-value'>{self._escape_html(sc.domain)}</span></div>")
            html_parts.append(f"<div class='context-item'><span class='context-label'>SO Tipo</span><span class='context-value'>{self._escape_html(sc.os_type)}</span></div>")
            if sc.os_version:
                html_parts.append(f"<div class='context-item'><span class='context-label'>Version SO</span><span class='context-value'>{self._escape_html(sc.os_version)}</span></div>")
            html_parts.append(f"<div class='context-item'><span class='context-label'>Uptime</span><span class='context-value'>{sc.uptime_hours} horas</span></div>")
            html_parts.append(f"<div class='context-item'><span class='context-label'>Virtual</span><span class='context-value'>{'Sí' if sc.is_virtual else 'No'}</span></div>")
            html_parts.append(f"<div class='context-item'><span class='context-label'>Bateria</span><span class='context-value'>{'Sí' if sc.has_battery else 'No'}</span></div>")
            html_parts.append(f"<div class='context-item'><span class='context-label'>WiFi</span><span class='context-value'>{'Sí' if sc.has_wifi else 'No'}</span></div>")
            html_parts.append("</div></div>")

        # Tabla de colectores con timestamps
        if diagnostic.collector_results:
            html_parts.append("<div class='collectors'>")
            html_parts.append("<h3>\u23F0 Timestamps de Colectores</h3>")
            html_parts.append("<table class='collector-table'><thead><tr><th>Colector</th><th>Timestamp</th><th>Duracion</th><th>Estado</th></tr></thead><tbody>")
            for cr in diagnostic.collector_results:
                timestamp = cr.captured_at_utc or "N/A"
                duration = f"{cr.query.duration_ms}ms" if cr.query.duration_ms else "N/A"
                status = cr.query.status or "unknown"
                html_parts.append(f"<tr><td>{self._escape_html(cr.collector_id)}</td><td>{self._escape_html(timestamp)}</td><td>{duration}</td><td>{self._escape_html(status)}</td></tr>")
            html_parts.append("</tbody></table></div>")

        # Resumen con contadores
        html_parts.append("<div class='summary'>")
        html_parts.append("<h3>\U0001F4CA Resumen</h3>")
        html_parts.append("<div class='summary-grid'>")
        html_parts.append(f"<div class='summary-item'><div class='summary-count'>{summary['total_collectors']}</div><div class='summary-label'>Total</div></div>")
        html_parts.append(f"<div class='summary-item'><div class='summary-count'>{summary['critical_count']}</div><div class='summary-label'>Críticos</div></div>")
        html_parts.append(f"<div class='summary-item'><div class='summary-count'>{summary['error_count']}</div><div class='summary-label'>Errores</div></div>")
        html_parts.append(f"<div class='summary-item'><div class='summary-count'>{summary['warning_count']}</div><div class='summary-label'>Advertencias</div></div>")
        html_parts.append(f"<div class='summary-item'><div class='summary-count'>{summary['ok_count']}</div><div class='summary-label'>OK</div></div>")
        html_parts.append("</div></div>")

        # Hallazgos
        html_parts.append("<div class='findings'>")
        if not diagnostic.findings:
            html_parts.append("<div class='finding ok'><span class='severity ok'>OK</span>No se encontraron problemas.</div>")
        else:
            for finding in diagnostic.findings:
                severity_class = finding.severity
                severity_label = SEVERIDAD_LABEL.get(finding.severity, finding.severity.upper())
                message = self._escape_html(finding.message)

                html_parts.append(f"<div class='finding {severity_class}'>")
                html_parts.append(f"<span class='severity {severity_class}'>{severity_label}</span>")
                html_parts.append(f"<div class='message'>{message}</div>")

                if finding.details:
                    html_parts.append("<div class='details'><table>")
                    for key, value in finding.details.items():
                        html_parts.append(f"<tr><td>{self._escape_html(str(key))}</td><td>{self._escape_html(str(value))}</td></tr>")
                    html_parts.append("</table></div>")

                html_parts.append("</div>")

        html_parts.append("</div>")  # findings

        if diagnostic.recommendations:
            html_parts.append("<div class='recommendations'>")
            html_parts.append("<h3>Recomendaciones</h3>")
            html_parts.append("<ul>")
            for rec in diagnostic.recommendations:
                html_parts.append(f"<li>{self._escape_html(rec)}</li>")
            html_parts.append("</ul>")
            html_parts.append("</div>")

        html_parts.extend([
            "</div>",  # content
            f"<div class='footer'>DiagUSB - Herramienta de Diagnóstico<br>Generado: {generation_time}<br>Copyright (C) 2026 Daniel Ricardo Novoa</div>",
            "</div>",  # container
            "</body>",
            "</html>"
        ])

        html = "\n".join(html_parts)

        if output_path:
            with open(output_path, "w", encoding="utf-8") as f:
                f.write(html)

        return html

    def generate_summary(self, diagnostic: DiagnosticResult) -> dict:
        """
        Genera un resumen del diagnostico.

        Args:
            diagnostic: Resultado del diagnostico.

        Returns:
            Diccionario con contadores de severidad.
        """
        counters = {
            "total_collectors": len(diagnostic.findings),
            "collectors_by_status": {},
            "critical_count": 0,
            "error_count": 0,
            "warning_count": 0,
            "ok_count": 0,
        }

        for finding in diagnostic.findings:
            severity = finding.severity
            counters["collectors_by_status"][severity] = counters["collectors_by_status"].get(severity, 0) + 1

            if severity == "critical":
                counters["critical_count"] += 1
            elif severity == "error":
                counters["error_count"] += 1
            elif severity == "warning":
                counters["warning_count"] += 1
            elif severity == "ok":
                counters["ok_count"] += 1

        return counters

    def _escape_html(self, text: str) -> str:
        """Escapa caracteres HTML."""
        return (text
                .replace("&", "&amp;")
                .replace("<", "&lt;")
                .replace(">", "&gt;")
                .replace('"', "&quot;")
                .replace("'", "&#39;"))


def generate_report(diagnostic: DiagnosticResult, output_dir: Path) -> Path:
    """
    Genera un reporte completo usando ambos reporters.

    Args:
        diagnostic: Resultado del diagnostico.
        output_dir: Directorio donde guardar los reportes.

    Returns:
        Ruta del archivo HTML generado.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generar reporte HTML
    html_reporter = HtmlReporter()
    timestamp = diagnostic.symptom.replace(" ", "_").lower()
    html_path = output_dir / f"diagnostico_{timestamp}.html"
    html_reporter.render(diagnostic, html_path)

    # Imprimir a consola
    console_reporter = ConsoleReporter()
    print(console_reporter.render(diagnostic))

    return html_path
