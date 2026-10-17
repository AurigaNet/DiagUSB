
        let isRunning = false;
        let currentDiag = null;
        let lastDiffs = null;
        let lastComparacionForzada = false;

        function escHtml(s) {
            const d = document.createElement('div');
            d.textContent = s == null ? '' : String(s);
            return d.innerHTML;
        }

        function formKey(f) {
            return [f.package_label || '', f.severity || '', f.collector_id || '', f.message || ''].join('|');
        }

        function loadForm() {
            try { return JSON.parse(localStorage.getItem('diagusb_form') || '{}') || {}; }
            catch (e) { return {}; }
        }

        function saveForm() {
            const data = loadForm();
            data.tecnico = (document.getElementById('tecnico') || {}).value || '';
            data.cliente = (document.getElementById('cliente') || {}).value || '';
            data.observaciones = (document.getElementById('observaciones') || {}).value || '';
            data.problemas = data.problemas || {};
            const findings = (currentDiag && currentDiag.findings) || [];
            findings.forEach((f, i) => {
                const key = formKey(f);
                const sols = f.solutions || [];
                data.problemas[key] = {
                    estado: (document.getElementById('estado_' + i) || {}).value || '',
                    solucion: (document.getElementById('solucion_' + i) || {}).value || '',
                    soluciones: sols.map((s, j) => {
                        const el = document.getElementById('sol_' + i + '_' + j);
                        return (el && el.checked) ? j : -1;
                    }).filter(x => x >= 0)
                };
            });
            data.mejoras = data.mejoras || {};
            ((currentDiag && currentDiag.improvements) || []).forEach((m, i) => {
                data.mejoras[m.id] = {
                    aplicada: !!((document.getElementById('mejora_' + i) || {}).checked),
                    comentario: (document.getElementById('mejora_coment_' + i) || {}).value || ''
                };
            });
            try { localStorage.setItem('diagusb_form', JSON.stringify(data)); } catch (e) {}
        }

        function applyForm() {
            const data = loadForm();
            if (data.tecnico != null) document.getElementById('tecnico').value = data.tecnico;
            if (data.cliente != null) document.getElementById('cliente').value = data.cliente;
            if (data.observaciones != null) document.getElementById('observaciones').value = data.observaciones;
            const saved = data.problemas || {};
            const findings = (currentDiag && currentDiag.findings) || [];
            findings.forEach((f, i) => {
                const st = saved[formKey(f)];
                if (!st) return;
                const sel = document.getElementById('estado_' + i);
                if (sel && st.estado) sel.value = st.estado;
                const inp = document.getElementById('solucion_' + i);
                if (inp && st.solucion) inp.value = st.solucion;
                (st.soluciones || []).forEach(j => {
                    const cb = document.getElementById('sol_' + i + '_' + j);
                    if (cb) cb.checked = true;
                });
            });
            const ms = data.mejoras || {};
            ((currentDiag && currentDiag.improvements) || []).forEach((m, i) => {
                const st = ms[m.id];
                if (!st) return;
                const cb = document.getElementById('mejora_' + i);
                if (cb) cb.checked = !!st.aplicada;
                const com = document.getElementById('mejora_coment_' + i);
                if (com && st.comentario) com.value = st.comentario;
            });
        }

        function hideAcciones() {
            currentDiag = null;
            lastDiffs = null;
            lastComparacionForzada = false;
            document.getElementById('accionesSection').style.display = 'none';
            document.getElementById('btnWord').style.display = 'none';
            document.getElementById('btnPdf').style.display = 'none';
            document.getElementById('btnSnapAntes').style.display = 'none';
            document.getElementById('btnSnapCompara').style.display = 'none';
            document.getElementById('diffSection').style.display = 'none';
        }
        
        function renderProblemas(findings) {
            const section = document.getElementById('accionesSection');
            const titulo = document.getElementById('accionesTitulo');
            const lista = document.getElementById('problemasLista');
            const mejorasLista = document.getElementById('mejorasLista');
            const colores = {critical: '#b00020', error: '#d93025', warning: '#e37400', ok: '#188038'};
            const sevLabel = {critical: 'CRITICO', error: 'ERROR', warning: 'ADVERTENCIA', ok: 'OK'};
            const estados = (currentDiag && currentDiag.estados_accion) ||
                ['Pendiente', 'Resuelto', 'Resuelto parcialmente', 'No reproducido', 'Requiere repuestos', 'Derivado / escalar'];
            
            if (!findings || findings.length === 0) {
                lista.innerHTML = '';
                titulo.textContent = 'Acciones del técnico - Generación de informe';
            } else {
                titulo.textContent = 'Problemas detectados y base de conocimiento - Acciones del técnico';
                let html = '';
                findings.forEach((f, i) => {
                    const color = colores[f.severity] || '#888';
                    const gt = (f.details && f.details.grupo_total) || 0;
                    const gmens = (f.details && f.details.grupo_mensajes) || [];
                    html += '<div class="problema-item" style="border-left-color:' + color + ';">';
                    html += '<div class="problema-titulo"><span class="diag-badge" style="background:' + color + '; color:#fff;">' +
                        escHtml(sevLabel[f.severity] || f.severity) + '</span> ' + escHtml(f.message) +
                        (gt > 1 ? '<span class="badge-grupo" title="Casos agrupados con el mismo problema">×' + gt + '</span>' : '') +
                        ' <span class="muted">(' + escHtml(f.package_label ? f.package_label + ' / ' : '') + escHtml(f.collector_id) + ')</span></div>';
                    if (gmens.length > 0) {
                        html += '<details class="grupo-extra"><summary>' + gmens.length +
                            ' caso(s) más del mismo problema</summary><ul>';
                        gmens.forEach(m => { html += '<li>' + escHtml(m) + '</li>'; });
                        html += '</ul></details>';
                    }
                    const kbinfo = f.knowledge;
                    if (kbinfo && kbinfo.estado_esperado) {
                        html += '<div class="kb-box">';
                        html += '<div class="kb-line"><b>Cómo debe estar:</b> ' + escHtml(kbinfo.estado_esperado) + '</div>';
                        if (kbinfo.por_que_importa) {
                            html += '<div class="kb-line kb-muted"><b>Por qué importa:</b> ' + escHtml(kbinfo.por_que_importa) + '</div>';
                        }
                        if (kbinfo.verificacion) {
                            html += '<div class="kb-line"><b>Cómo verificar que quedó bien:</b> ' + escHtml(kbinfo.verificacion) + '</div>';
                        }
                        html += '</div>';
                    }
                    const sols = f.solutions || [];
                    if (sols.length > 0) {
                        html += '<div class="soluciones-box"><div class="acciones-hint">' +
                            (kbinfo && kbinfo.id ? 'Pasos de corrección según la base de conocimiento - marque la(s) que aplicó:' :
                             'Soluciones posibles - marque la(s) que aplicó:') + '</div>';
                        sols.forEach((s, j) => {
                            html += '<label class="opcion"><input type="checkbox" id="sol_' + i + '_' + j + '" value="' +
                                escHtml(s) + '"> <span>' + escHtml(s) + '</span></label>';
                        });
                        html += '</div>';
                    }
                    html += '<div class="problema-accion">';
                    html += '<select id="estado_' + i + '">' +
                        estados.map(e => '<option value="' + escHtml(e) + '">' + escHtml(e) + '</option>').join('') +
                        '</select>';
                    html += '<input id="solucion_' + i + '" type="text" style="flex:1; min-width:240px;" placeholder="Detalle de la acción implementada (opcional)...">';
                    html += '</div></div>';
                });
                lista.innerHTML = html;
            }
            
            // Mejoras sugeridas
            const mejoras = (currentDiag && currentDiag.improvements) || [];
            if (mejoras.length === 0) {
                mejorasLista.innerHTML = '';
            } else {
                let mh = '<div class="mejoras-title">Mejoras sugeridas (marque las que implementó):</div>';
                mejoras.forEach((m, i) => {
                    mh += '<div class="problema-item" style="border-left-color:#4facfe;">';
                    mh += '<label class="opcion"><input type="checkbox" id="mejora_' + i + '"> <span><b>' +
                        escHtml(m.titulo) + '</b></span></label>';
                    mh += '<div class="acciones-hint">' + escHtml(m.detalle) + '</div>';
                    mh += '<input id="mejora_coment_' + i + '" type="text" style="width:100%; margin-top:6px;" placeholder="Comentario sobre la mejora (opcional)...">';
                    mh += '</div>';
                });
                mejorasLista.innerHTML = mh;
            }

            section.style.display = 'block';
            document.getElementById('btnWord').style.display = '';
            document.getElementById('btnPdf').style.display = '';
            document.getElementById('btnSnapAntes').style.display = '';
            document.getElementById('btnSnapCompara').style.display = '';
            applyForm();
        }
        
        function collectPayload() {
            const findings = (currentDiag && currentDiag.findings) || [];
            const acciones = findings.map((f, i) => {
                const sols = f.solutions || [];
                const elegidas = sols
                    .map((s, j) => ({s: s, el: document.getElementById('sol_' + i + '_' + j)}))
                    .filter(x => x.el && x.el.checked)
                    .map(x => x.s);
                return {
                    indice: i + 1,
                    estado: (document.getElementById('estado_' + i) || {}).value || 'Pendiente',
                    solucion_elegida: elegidas.join('; '),
                    solucion: (document.getElementById('solucion_' + i) || {}).value || ''
                };
            });
            const mejoras = ((currentDiag && currentDiag.improvements) || []).map((m, i) => ({
                id: m.id,
                aplicada: !!((document.getElementById('mejora_' + i) || {}).checked),
                comentario: (document.getElementById('mejora_coment_' + i) || {}).value || ''
            }));
            return {
                diagnostico: currentDiag,
                acciones: acciones,
                mejoras: mejoras,
                tecnico: (document.getElementById('tecnico') || {}).value || '',
                cliente: (document.getElementById('cliente') || {}).value || '',
                observaciones: (document.getElementById('observaciones') || {}).value || '',
                diferencias: lastDiffs || [],
                comparacion_forzada: !!lastComparacionForzada
            };
        }

        async function saveSnapshotAntes() {
            if (!currentDiag) return;
            setStatus('running', 'Guardando snapshot ANTES...');
            try {
                const resp = await fetch('/api/snapshot', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({results: currentDiag.results || []})
                });
                const d = await resp.json();
                if (!resp.ok) throw new Error(d.error || ('HTTP ' + resp.status));
                setStatus('ready', 'Snapshot ANTES guardado (' + d.collectors + ' colectores, ' + d.captured_at.slice(0, 19) + ')');
            } catch (e) {
                setStatus('error', 'Error al guardar el snapshot: ' + e.message);
            }
        }

        function renderDiff(diffs, baselineEn) {
            const sec = document.getElementById('diffSection');
            const el = document.getElementById('diffTabla');
            lastDiffs = diffs || [];
            let html = '<div class="acciones-hint">Snapshot de referencia: ' + escHtml(baselineEn || '-') + '</div>';
            if (!lastDiffs.length) {
                html += '<div class="diff-sin-cambios">✓ Sin cambios entre el estado ANTES y el actual.</div>';
            } else {
                html += '<table class="diff-table"><tr><th>Colector</th><th>Campo</th><th>Antes</th><th>Después</th></tr>';
                lastDiffs.forEach(d => {
                    const fmt = v => {
                        if (v && typeof v === 'object') return '[' + (Array.isArray(v) ? v.length + ' registros' : Object.keys(v).length + ' campos') + ']';
                        const s = v == null ? '-' : String(v);
                        return s.length > 140 ? s.slice(0, 137) + '...' : s;
                    };
                    html += '<tr><td>' + escHtml(d.collector_id || '') + '</td><td>' + escHtml(d.field_path || '') +
                        '</td><td>' + escHtml(fmt(d.baseline_value)) + '</td><td>' + escHtml(fmt(d.current_value)) + '</td></tr>';
                });
                html += '</table>';
            }
            el.innerHTML = html;
            sec.style.display = 'block';
            sec.scrollIntoView({behavior: 'smooth', block: 'nearest'});
        }

        async function compareSnapshot(forzar) {
            if (!currentDiag) return;
            setStatus('running', 'Comparando contra el snapshot ANTES...');
            try {
                const resp = await fetch('/api/compare', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({results: currentDiag.results || [], forzar: !!forzar})
                });
                const d = await resp.json();
                if (resp.status === 409) {
                    const msg = d.error || 'El snapshot ANTES pertenece a otro equipo.';
                    if (confirm(msg + '  ¿Comparar de todos modos?')) {
                        return compareSnapshot(true);
                    }
                    setStatus('ready', 'Comparación cancelada por el técnico.');
                    return;
                }
                if (!resp.ok) throw new Error(d.error || ('HTTP ' + resp.status));
                lastComparacionForzada = !!d.equipos_distintos;
                renderDiff(d.diferencias || [], d.baseline_en);
                let texto = 'Comparación lista: ' + (lastDiffs ? lastDiffs.length : 0) + ' diferencia(s). Incluirán en el informe.';
                if (lastComparacionForzada) {
                    texto = 'ADVERTENCIA: comparación entre equipos distintos. ' + texto;
                } else if (d.advertencia) {
                    texto = d.advertencia + ' ' + texto;
                }
                setStatus(lastComparacionForzada ? 'error' : 'ready', texto);
            } catch (e) {
                setStatus('error', 'Error al comparar: ' + e.message);
            }
        }
        
        async function downloadReport(format) {
            if (!currentDiag) {
                alert('Ejecute primero un diagnóstico individual (no la Revisión Total).');
                return;
            }
            setStatus('running', 'Generando informe ' + format.toUpperCase() + '...');
            try {
                const resp = await fetch('/api/report?format=' + format, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(collectPayload())
                });
                if (!resp.ok) {
                    const err = await resp.json().catch(() => ({}));
                    throw new Error(err.error || ('HTTP ' + resp.status));
                }
                const blob = await resp.blob();
                const cd = resp.headers.get('Content-Disposition') || '';
                const m = cd.match(/filename="?([^";]+)/);
                const a = document.createElement('a');
                a.href = URL.createObjectURL(blob);
                a.download = m ? m[1] : 'informe.' + format;
                document.body.appendChild(a);
                a.click();
                a.remove();
                URL.revokeObjectURL(a.href);
                setStatus('ready', 'Informe ' + format.toUpperCase() + ' descargado');
            } catch (e) {
                setStatus('error', 'Error al generar informe: ' + e.message);
            }
        }
        
        function mostrarIntegridad(lista) {
            const b = document.getElementById('integridadBanner');
            if (!b) return;
            if (lista && lista.length) {
                b.textContent = 'Integridad: ' + lista.length + ' colector(es) modificado(s): ' +
                    lista.join(', ') + '. No se ejecutaron. Regenere el kit desde una copia confiable.';
                b.style.display = 'block';
            } else {
                b.style.display = 'none';
            }
        }

        function setStatus(status, text) {
            const dot = document.getElementById('statusDot');
            const textEl = document.getElementById('statusText');
            dot.className = 'status-dot ' + status;
            textEl.textContent = text;
        }
        
        function showLoading(message) {
            return '<div class="loading"><div class="spinner"></div><p class="loading-text">' + message + '</p></div>';
        }
        
        function formatJson(data) {
            try {
                return JSON.stringify(data, null, 2);
            } catch (e) {
                return String(data);
            }
        }
        
        function getStatusBadge(ok, errors, problems, empty) {
            problems = problems || 0;
            empty = empty || 0;
            if (errors > 0) return '<span class="diag-badge error">' + errors + ' error(es)</span>';
            if (problems > 0) return '<span class="diag-badge error">' + problems + ' problema(s)</span>';
            if (ok > 0) return '<span class="diag-badge ok">OK</span>';
            if (empty > 0) return '<span class="diag-badge warning">Sin datos: ' + empty + '</span>';
            return '<span class="diag-badge warning">Sin datos</span>';
        }
        
        async function runDiagnostic(package) {
            if (isRunning) return;
            isRunning = true;
            
            const buttons = document.querySelectorAll('.btn:not(#btnKb):not(#btnRegistro)');
            buttons.forEach(b => b.disabled = true);
            
            setStatus('running', 'Ejecutando diagnóstico de ' + package + '...');
            document.getElementById('resultsContent').innerHTML = showLoading('Ejecutando colectores...');
            
            try {
                const response = await fetch('/api/diagnose?package=' + encodeURIComponent(package));
                const data = await response.json();
                
                if (data.error) {
                    hideAcciones();
                    mostrarIntegridad([]);
                    document.getElementById('resultsContent').innerHTML = '<div class="diag-card error"><p>' + data.error + '</p></div>';
                    setStatus('error', 'Error: ' + data.error);
                } else {
                    currentDiag = data;
                    lastDiffs = null;
                    lastComparacionForzada = false;
                    mostrarIntegridad(data.integridad_fallida);
                    document.getElementById('diffSection').style.display = 'none';
                    const nProblemas = (data.findings || []).length;
                    renderProblemas(data.findings || []);
                    let html = '<div class="diag-card ' + ((data.error_count > 0 || nProblemas > 0) ? 'warning' : 'success') + '">';
                    html += '<div class="diag-header">';
                    html += '<span class="diag-title">' + data.package_label + '</span>';
                    html += getStatusBadge(data.ok_count, data.error_count, nProblemas, data.empty_count);
                    html += '</div>';
                    html += '<div class="diag-stats">';
                    html += '<span>Colectores: ' + data.collectors_count + '</span>';
                    html += '<span>OK: ' + data.ok_count + '</span>';
                    html += '<span>Errores: ' + data.error_count + '</span>';
                    html += '<span>Sin datos: ' + (data.empty_count || 0) + '</span>';
                    html += '<span>Problemas: ' + nProblemas + '</span>';
                    html += '<span>' + data.timestamp + '</span>';
                    html += '</div>';
                    
                    // Mostrar resultados expandidos
                    for (const result of data.results) {
                        const status = result.query?.status || 'unknown';
                        const cardClass = status === 'ok' ? 'success' : (status === 'error' ? 'error' : 'warning');
                        html += '<div class="diag-card ' + cardClass + '" style="margin-top: 12px; border-left-width: 2px;">';
                        html += '<div class="diag-header">';
                        html += '<span class="diag-title">' + (result.collector_id || 'unknown') + '</span>';
                        html += '<span class="diag-badge ' + (status === 'ok' ? 'ok' : 'error') + '">' + status + '</span>';
                        html += '</div>';
                        html += '<div class="diag-json">' + formatJson(result.data || result) + '</div>';
                        html += '</div>';
                    }
                    
                    html += '</div>';
                    document.getElementById('resultsContent').innerHTML = html;
                    setStatus('ready', 'Diagnóstico completado: ' + data.package_label +
                        (data.registro_id ? ' · guardado en registro' : ''));
                }
            } catch (e) {
                hideAcciones();
                document.getElementById('resultsContent').innerHTML = '<div class="diag-card error"><p>Error: ' + e.message + '</p></div>';
                setStatus('error', 'Error de conexión');
            }
            
            buttons.forEach(b => b.disabled = false);
            isRunning = false;
        }
        
        async function runFullScan() {
            if (isRunning) return;
            isRunning = true;
            hideAcciones();
            
            const buttons = document.querySelectorAll('.btn:not(#btnKb):not(#btnRegistro)');
            buttons.forEach(b => b.disabled = true);
            
            setStatus('running', 'Ejecutando revisión total del equipo...');
            document.getElementById('resultsContent').innerHTML = showLoading('Ejecutando todos los diagnósticos...');
            
            try {
                const response = await fetch('/api/full-scan');
                const data = await response.json();
                
                const integridadTotal = [];
                (data.diagnostics || []).forEach(dg => (dg.integridad_fallida || []).forEach(x => {
                    if (integridadTotal.indexOf(x) === -1) integridadTotal.push(x);
                }));
                mostrarIntegridad(integridadTotal);
                
                let html = '';
                let totalErrors = 0;
                let totalOk = 0;
                let totalEmpty = 0;
                let totalProblems = 0;
                let totalCollectors = 0;
                const allFindings = [];
                const allImprovements = [];
                const allResults = [];
                const allRecommendations = [];
                const seenMejoras = {};
                
                for (const diag of data.diagnostics) {
                    const errors = diag.error_count || 0;
                    const ok = diag.ok_count || 0;
                    const problems = (diag.findings || []).length;
                    totalErrors += errors;
                    totalOk += ok;
                    totalEmpty += (diag.empty_count || 0);
                    totalProblems += problems;
                    totalCollectors += diag.collectors_count || (diag.results || []).length;
                    
                    (diag.results || []).forEach(r => allResults.push(r));
                    (diag.findings || []).forEach(f => {
                        const c = Object.assign({}, f);
                        c.package_label = diag.package_label;
                        allFindings.push(c);
                    });
                    (diag.improvements || []).forEach(m => {
                        if (!seenMejoras[m.id]) {
                            seenMejoras[m.id] = true;
                            allImprovements.push(m);
                        }
                    });
                    (diag.recommendations || []).forEach(rc => {
                        if (allRecommendations.indexOf(rc) === -1) allRecommendations.push(rc);
                    });
                    
                    const cardClass = (errors > 0 || problems > 0) ? 'warning' : 'success';
                    html += '<div class="diag-card ' + cardClass + '">';
                    html += '<div class="diag-header">';
                    html += '<span class="diag-title">' + diag.package_label + '</span>';
                    html += getStatusBadge(ok, errors, problems, diag.empty_count);
                    html += '</div>';
                    html += '<div class="diag-stats">';
                    html += '<span>OK: ' + ok + '</span>';
                    html += '<span>Errores: ' + errors + '</span>';
                    html += '<span>Sin datos: ' + (diag.empty_count || 0) + '</span>';
                    html += '<span>Problemas: ' + problems + '</span>';
                    html += '</div>';
                    
                    // Mostrar colectores con problemas
                    for (const result of diag.results) {
                        const status = result.query?.status || 'unknown';
                        if (status === 'error') {
                            html += '<div class="diag-json" style="margin-top: 8px; padding: 8px;">';
                            html += '<strong>' + (result.collector_id || 'unknown') + ':</strong> ' + formatJson(result.data || result);
                            html += '</div>';
                        }
                    }
                    
                    html += '</div>';
                }
                
                // Resumen
                html = '<div class="diag-card ' + ((totalErrors > 0 || totalProblems > 0) ? 'warning' : 'success') + '" style="margin-bottom: 20px;">' +
                    '<div class="diag-header">' +
                    '<span class="diag-title">RESUMEN TOTAL</span>' +
                    getStatusBadge(totalOk, totalErrors, totalProblems, totalEmpty) +
                    '</div>' +
                    '<div class="diag-stats">' +
                    '<span>Paquetes: ' + data.diagnostics.length + '</span>' +
                    '<span>Colectores OK: ' + totalOk + '</span>' +
                    '<span>Colectores con error: ' + totalErrors + '</span>' +
                    '<span>Sin datos: ' + totalEmpty + '</span>' +
                    '<span>Problemas detectados: ' + totalProblems + '</span>' +
                    '</div>' +
                    '</div>' + html;

                // Seccion de acciones del tecnico e informe (igual que un diagnostico individual)
                lastDiffs = null;
                lastComparacionForzada = false;
                document.getElementById('diffSection').style.display = 'none';
                currentDiag = {
                    package: 'full-scan',
                    package_label: 'Revisión Total',
                    symptom: 'revision_total',
                    collectors_count: totalCollectors,
                    ok_count: totalOk,
                    error_count: totalErrors,
                    empty_count: totalEmpty,
                    findings: allFindings,
                    improvements: allImprovements,
                    results: allResults,
                    recommendations: allRecommendations,
                    estados_accion: (data.diagnostics[0] || {}).estados_accion,
                    timestamp: data.timestamp
                };
                renderProblemas(allFindings);
                
                document.getElementById('resultsContent').innerHTML = html;
                setStatus('ready', 'Revisión total completada' +
                    (data.registro_id ? ' · guardado en registro' : ''));
            } catch (e) {
                document.getElementById('resultsContent').innerHTML = '<div class="diag-card error"><p>Error: ' + e.message + '</p></div>';
                setStatus('error', 'Error de conexión');
            }
            
            buttons.forEach(b => b.disabled = false);
            isRunning = false;
        }
        
        function copyResults() {
            const content = document.getElementById('resultsContent').innerText;
            navigator.clipboard.writeText(content).then(() => {
                alert('Resultados copiados al portapapeles');
            });
        }
        
        function clearResults() {
            hideAcciones();
            document.getElementById('resultsContent').innerHTML = 
                '<div class="results-empty"><div class="results-empty-icon">🔧</div><p>Haga clic en un botón para ejecutar un diagnóstico</p></div>';
            setStatus('ready', 'Listo para ejecutar diagnósticos');
        }
        
        let kbEntradas = [];
        let kbRender = [];
        
        function renderKb(lista) {
            const el = document.getElementById('kbLista');
            if (!el) return;
            if (!kbEntradas.length) {
                el.innerHTML = '<p class="acciones-hint">Base de conocimiento no disponible (archivo base_conocimiento.json no encontrado o vacío).</p>';
                return;
            }
            if (!lista.length) {
                el.innerHTML = '<p class="acciones-hint">Sin resultados para esa búsqueda.</p>';
                return;
            }
            let html = '';
            kbRender = lista;
            lista.forEach((e, i) => {
                html += '<div class="kb-card">';
                html += '<div class="kb-cat">' + escHtml(e.categoria || 'General') + '</div>';
                html += '<h4>' + escHtml(e.titulo || e.id) + '</h4>';
                html += '<div class="kb-body">';
                if (e.estado_esperado) html += '<div><b>Cómo debe estar:</b> ' + escHtml(e.estado_esperado) + '</div>';
                if (e.por_que_importa) html += '<div class="kb-muted" style="color:#aaa; margin-top:4px;"><b>Por qué importa:</b> ' + escHtml(e.por_que_importa) + '</div>';
                if (e.soluciones && e.soluciones.length) {
                    html += '<div style="margin-top:6px;"><b>Solución:</b><ol>';
                    e.soluciones.forEach(s => { html += '<li>' + escHtml(s) + '</li>'; });
                    html += '</ol></div>';
                }
                if (e.verificacion) html += '<div style="margin-top:6px;"><b>Verificación:</b> ' + escHtml(e.verificacion) + '</div>';
                html += '</div>';
                html += '<div class="kb-card-actions">' +
                    '<button class="kb-edit" data-kb-idx="' + i + '">Editar</button>' +
                    '<button class="kb-del" data-kb-idx="' + i + '">Eliminar</button>' +
                    '</div>';
                html += '</div>';
            });
            el.innerHTML = html;
        }
        
        function filterKb() {
            const q = ((document.getElementById('kbSearch') || {}).value || '').trim().toLowerCase();
            if (!q) { renderKb(kbEntradas); return; }
            const lista = kbEntradas.filter(e =>
                JSON.stringify(e).toLowerCase().indexOf(q) !== -1);
            renderKb(lista);
        }
        
        async function loadKnowledge() {
            try {
                const r = await fetch('/api/knowledge');
                const d = await r.json();
                kbEntradas = d.entradas || [];
                renderKb(kbEntradas);
            } catch (e) {
                const el = document.getElementById('kbLista');
                if (el) el.innerHTML = '<p class="acciones-hint">No se pudo cargar la base de conocimiento.</p>';
            }
        }
        
        function toggleKb() {
            const sec = document.getElementById('kbSection');
            const btn = document.getElementById('btnKb');
            const abierto = sec.style.display === 'block';
            if (abierto) {
                sec.style.display = 'none';
                btn.classList.remove('btn-open');
                closeKbForm();
            } else {
                if (!kbEntradas.length) loadKnowledge();
                sec.style.display = 'block';
                btn.classList.add('btn-open');
                sec.scrollIntoView({behavior: 'smooth', block: 'start'});
            }
        }

        let kbEditId = null;

        function openKbForm(entrada) {
            const form = document.getElementById('kbForm');
            kbEditId = entrada ? entrada.id : null;
            document.getElementById('kbFormTitulo').textContent =
                entrada ? ('Editar entrada: ' + (entrada.titulo || entrada.id)) : 'Nueva entrada';
            document.getElementById('kbf_id').value = entrada ? (entrada.id || '') : '';
            document.getElementById('kbf_id').disabled = !!entrada;
            document.getElementById('kbf_titulo').value = entrada ? (entrada.titulo || '') : '';
            document.getElementById('kbf_categoria').value = entrada ? (entrada.categoria || '') : '';
            document.getElementById('kbf_colectores').value = entrada && entrada.colectores ? entrada.colectores.join(', ') : '';
            document.getElementById('kbf_sintomas').value = entrada && entrada.sintomas ? entrada.sintomas.join(', ') : '';
            document.getElementById('kbf_estado_esperado').value = entrada ? (entrada.estado_esperado || '') : '';
            document.getElementById('kbf_por_que_importa').value = entrada ? (entrada.por_que_importa || '') : '';
            document.getElementById('kbf_soluciones').value = entrada && entrada.soluciones ? entrada.soluciones.join('\n') : '';
            document.getElementById('kbf_verificacion').value = entrada ? (entrada.verificacion || '') : '';
            form.classList.add('open');
            form.scrollIntoView({behavior: 'smooth', block: 'nearest'});
        }

        function openKbFormById(id) {
            const e = kbEntradas.find(x => x.id === id);
            if (e) openKbForm(e);
        }

        function closeKbForm() {
            const form = document.getElementById('kbForm');
            if (form) form.classList.remove('open');
            kbEditId = null;
        }

        const splitCsv = v => (v || '').split(',').map(x => x.trim()).filter(Boolean);

        async function saveKbForm() {
            const id = kbEditId || (document.getElementById('kbf_id').value || '').trim().toLowerCase();
            const titulo = (document.getElementById('kbf_titulo').value || '').trim();
            if (!id || !titulo) {
                alert('El ID y el título son obligatorios.');
                return;
            }
            const entrada = {
                id: id,
                titulo: titulo,
                categoria: (document.getElementById('kbf_categoria').value || '').trim() || 'General',
                colectores: splitCsv(document.getElementById('kbf_colectores').value),
                sintomas: splitCsv(document.getElementById('kbf_sintomas').value),
                estado_esperado: document.getElementById('kbf_estado_esperado').value || '',
                por_que_importa: document.getElementById('kbf_por_que_importa').value || '',
                soluciones: (document.getElementById('kbf_soluciones').value || '').split('\n').map(x => x.trim()).filter(Boolean),
                verificacion: document.getElementById('kbf_verificacion').value || ''
            };
            try {
                const resp = await fetch('/api/knowledge', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({accion: 'guardar', entrada: entrada})
                });
                const d = await resp.json();
                if (!resp.ok) throw new Error(d.error || ('HTTP ' + resp.status));
                kbEntradas = d.entradas || [];
                closeKbForm();
                filterKb();
                setStatus('ready', 'Entrada de la base de conocimiento guardada (capa local)');
            } catch (e) {
                alert('No se pudo guardar: ' + e.message);
            }
        }

        async function deleteKb(id, titulo) {
            if (!confirm('¿Eliminar la entrada "' + titulo + '" de la base de conocimiento local?')) return;
            try {
                const resp = await fetch('/api/knowledge', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({accion: 'eliminar', id: id})
                });
                const d = await resp.json();
                if (!resp.ok) throw new Error(d.error || ('HTTP ' + resp.status));
                kbEntradas = d.entradas || [];
                filterKb();
                setStatus('ready', 'Entrada eliminada de la base de conocimiento local');
            } catch (e) {
                alert('No se pudo eliminar: ' + e.message);
            }
        }

        // ---------------------------------------------------------------
        // Registro persistente de análisis
        // ---------------------------------------------------------------
        let regEntradas = [];
        
        function renderRegistro(lista) {
            const el = document.getElementById('regLista');
            if (!el) return;
            const vaciar = document.getElementById('btnRegVaciar');
            if (vaciar) vaciar.style.display = regEntradas.length ? '' : 'none';
            if (!regEntradas.length) {
                el.innerHTML = '<p class="acciones-hint">Todavía no hay análisis registrados. Cada diagnóstico que ejecute quedará guardado automáticamente aquí.</p>';
                return;
            }
            if (!lista.length) {
                el.innerHTML = '<p class="acciones-hint">Sin resultados para esa búsqueda.</p>';
                return;
            }
            let html = '';
            lista.forEach(e => {
                const c = e.conteos || {};
                const fecha = (e.fecha || '').replace('T', ' ').slice(0, 19);
                const tipo = e.tipo === 'full-scan' ? 'Revisión total' : 'Paquete';
                html += '<div class="kb-card">';
                html += '<div class="kb-cat">' + escHtml(tipo) + ' · ' + escHtml(fecha) + '</div>';
                html += '<h4>' + escHtml(e.paquete_label || e.paquete || '-') + '</h4>';
                html += '<div class="kb-body">';
                html += '<div><b>Síntoma:</b> ' + escHtml(e.sintoma || '-') + '</div>';
                html += '<div style="margin-top:4px;">Colectores OK: ' + (c.ok || 0) +
                    ' · Con error: ' + (c.error || 0) +
                    ' · Sin datos: ' + (c.empty || 0) +
                    ' · <b>Problemas: ' + (c.findings || 0) + '</b></div>';
                html += '<div id="regdet_' + e.id + '" style="display:none; margin-top:8px;"></div>';
                html += '</div>';
                html += '<div class="kb-card-actions">' +
                    '<button class="reg-det" data-reg-det="' + e.id + '">Ver detalle</button>' +
                    '<button class="kb-del" data-reg-del="' + e.id + '">Eliminar</button>' +
                    '</div>';
                html += '</div>';
            });
            el.innerHTML = html;
            el.querySelectorAll('[data-reg-del]').forEach(b =>
                b.addEventListener('click', () => eliminarRegistro(b.getAttribute('data-reg-del'))));
            el.querySelectorAll('[data-reg-det]').forEach(b =>
                b.addEventListener('click', () => toggleRegDetalle(b.getAttribute('data-reg-det'), b)));
        }
        
        async function toggleRegDetalle(id, btn) {
            const cont = document.getElementById('regdet_' + id);
            if (!cont) return;
            if (cont.style.display === 'block') {
                cont.style.display = 'none';
                btn.textContent = 'Ver detalle';
                return;
            }
            if (!cont.innerHTML) {
                try {
                    const r = await fetch('/api/registro?id=' + encodeURIComponent(id));
                    const d = await r.json();
                    if (d.error) throw new Error(d.error);
                    let h = '';
                    const findings = d.findings || [];
                    if (!findings.length) {
                        h += '<div class="acciones-hint">Sin problemas detectados en ese análisis.</div>';
                    }
                    findings.forEach(f => {
                        const color = f.severity === 'error' ? '#ff6b6b' :
                                     (f.severity === 'warning' ? '#ffd166' : '#8ef0a0');
                        h += '<div style="margin-bottom:6px; border-left:3px solid ' + color + '; padding-left:8px;">';
                        h += '<b style="color:' + color + '; text-transform:uppercase; font-size:11px;">' +
                            escHtml(f.severity || '') + '</b> ';
                        if (f.package_label) h += '<span class="acciones-hint">[' + escHtml(f.package_label) + '] </span>';
                        h += '<span class="acciones-hint">(' + escHtml(f.collector_id || '') + ')</span><br>';
                        h += escHtml(f.message || '');
                        if (f.solutions && f.solutions.length) {
                            h += '<ul style="margin:4px 0 0 16px;">';
                            f.solutions.forEach(s => { h += '<li style="font-size:12px;">' + escHtml(s) + '</li>'; });
                            h += '</ul>';
                        }
                        h += '</div>';
                    });
                    if (d.recommendations && d.recommendations.length) {
                        h += '<div style="margin-top:6px;"><b>Recomendaciones:</b><ul style="margin:4px 0 0 16px;">';
                        d.recommendations.forEach(rc => { h += '<li style="font-size:12px;">' + escHtml(rc) + '</li>'; });
                        h += '</ul></div>';
                    }
                    if (d.colectores && d.colectores.length) {
                        h += '<div class="acciones-hint" style="margin-top:6px;">Colectores: ';
                        h += d.colectores.map(c => escHtml(c.id) + ' [' + escHtml(c.status) + ']').join(' · ');
                        h += '</div>';
                    }
                    cont.innerHTML = h;
                } catch (e) {
                    cont.innerHTML = '<p class="acciones-hint">No se pudo cargar el detalle: ' + escHtml(e.message) + '</p>';
                }
            }
            cont.style.display = 'block';
            btn.textContent = 'Ocultar';
        }
        
        async function loadRegistro() {
            try {
                const r = await fetch('/api/registro');
                const d = await r.json();
                regEntradas = d.entradas || [];
                const lbl = document.querySelector('#btnRegistro .btn-label');
                if (lbl) {
                    lbl.textContent = regEntradas.length ?
                        ('Registro de análisis (' + regEntradas.length + ')') :
                        'Registro de análisis';
                }
                filterRegistro();
            } catch (e) {
                const el = document.getElementById('regLista');
                if (el) el.innerHTML = '<p class="acciones-hint">No se pudo cargar el registro.</p>';
            }
        }
        
        function filterRegistro() {
            const q = ((document.getElementById('regSearch') || {}).value || '').trim().toLowerCase();
            if (!q) { renderRegistro(regEntradas); return; }
            const lista = regEntradas.filter(e =>
                JSON.stringify(e).toLowerCase().indexOf(q) !== -1);
            renderRegistro(lista);
        }
        
        function toggleRegistro() {
            const sec = document.getElementById('registroSection');
            const btn = document.getElementById('btnRegistro');
            const abierto = sec.style.display === 'block';
            if (abierto) {
                sec.style.display = 'none';
                btn.classList.remove('btn-open');
            } else {
                loadRegistro();
                sec.style.display = 'block';
                btn.classList.add('btn-open');
                sec.scrollIntoView({behavior: 'smooth', block: 'start'});
            }
        }
        
        async function eliminarRegistro(id) {
            if (!confirm('¿Eliminar este análisis del registro?')) return;
            try {
                const r = await fetch('/api/registro?id=' + encodeURIComponent(id), {method: 'DELETE'});
                const d = await r.json();
                if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
                setStatus('ready', 'Análisis eliminado del registro');
                await loadRegistro();
            } catch (e) {
                setStatus('error', 'Error al eliminar: ' + e.message);
            }
        }
        
        async function vaciarRegistro() {
            if (!regEntradas.length) return;
            if (!confirm('¿Eliminar TODOS los análisis del registro (' + regEntradas.length +
                         ')? Esta acción no se puede deshacer.')) return;
            try {
                const r = await fetch('/api/registro', {method: 'DELETE'});
                const d = await r.json();
                if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
                setStatus('ready', 'Registro vaciado (' + d.eliminados + ' análisis eliminados)');
                await loadRegistro();
            } catch (e) {
                setStatus('error', 'Error al vaciar: ' + e.message);
            }
        }
        
        async function loadElevation() {
            try {
                const r = await fetch('/api/elevation');
                const d = await r.json();
                const b = document.getElementById('elevBanner');
                const rb = document.getElementById('respaldoBanner');
                if (rb) {
                    if (d.respaldo) {
                        rb.textContent = 'Aviso: la carpeta junto al ejecutable no es escribible; los datos (config/ y reports/) se guardan en ' + d.ruta_base + '.';
                        rb.style.display = 'block';
                    } else {
                        rb.style.display = 'none';
                    }
                }
                if (d.is_elevated === true) {
                    b.className = 'elev-banner ok';
                    b.innerHTML = '<b>Permisos de Administrador:</b> activos. Los colectores pueden leer inventario completo (software, discos, eventos).';
                    b.style.display = 'block';
                } else if (d.is_elevated === false) {
                    b.className = 'elev-banner warn';
                    b.innerHTML = '<b>Modo estándar:</b> datos limitados: installed_software (requiere administrador); ' +
                        'los eventos de seguridad no se evalúan. ' +
                        '<button type="button" class="elev-btn" id="elevBtn">Dar permisos de administrador</button>' +
                        '<div class="elev-msg" id="elevMsg"></div>';
                    b.style.display = 'block';
                    const eb = document.getElementById('elevBtn');
                    if (eb) eb.addEventListener('click', solicitarElevacion);
                }
            } catch (e) {}
        }

        async function solicitarElevacion() {
            const btn = document.getElementById('elevBtn');
            const msg = document.getElementById('elevMsg');
            if (btn) { btn.disabled = true; btn.textContent = 'Solicitando permisos...'; }
            if (msg) msg.textContent = '';
            try {
                const r = await fetch('/api/elevar', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: '{}'
                });
                const d = await r.json();
                if (d.ok) {
                    if (msg) msg.textContent = d.mensaje || ('Se abrió otra pestaña con permisos en el puerto ' + d.puerto + '.');
                } else {
                    if (msg) msg.textContent = d.error || d.mensaje || 'No se otorgaron los permisos.';
                    if (btn) { btn.disabled = false; btn.textContent = 'Dar permisos de administrador'; }
                }
            } catch (e) {
                if (msg) msg.textContent = 'Error: ' + e.message;
                if (btn) { btn.disabled = false; btn.textContent = 'Dar permisos de administrador'; }
            }
        }

        document.addEventListener('DOMContentLoaded', () => {
            const s = document.getElementById('kbSearch');
            if (s) s.addEventListener('input', filterKb);
            ['tecnico', 'cliente', 'observaciones'].forEach(id => {
                const el = document.getElementById(id);
                if (el) el.addEventListener('input', saveForm);
            });
            document.addEventListener('change', ev => {
                const t = ev.target;
                if (t && t.id && /^(estado_|solucion_|sol_|mejora_)/.test(t.id)) saveForm();
            });
            document.addEventListener('input', ev => {
                const t = ev.target;
                if (t && t.id && /^(solucion_|mejora_coment_)/.test(t.id)) saveForm();
            });
            const kbl = document.getElementById('kbLista');
            if (kbl) kbl.addEventListener('click', ev => {
                const b = ev.target.closest('button[data-kb-idx]');
                if (!b) return;
                const e = kbRender[parseInt(b.getAttribute('data-kb-idx'), 10)];
                if (!e) return;
                if (b.classList.contains('kb-del')) {
                    deleteKb(e.id, e.titulo || e.id);
                } else {
                    openKbForm(e);
                }
            });
            loadElevation();
        });
