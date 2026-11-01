/* SPDX-License-Identifier: GPL-3.0-or-later */

        let isRunning = false;
        let capacidadesActuales = null;
        let currentDiag = null;
        let lastDiffs = null;
        let lastComparacionForzada = false;
        let lastMetricasBase = null;
        let lastMetricasActual = null;

        const pruebaPerifericos = {
            activa: false,
            prueba_ejecutada: false,
            iniciada_en: '',
            finalizada_en: '',
            teclas: 0,
            ultima_tecla: '',
            ultimo_codigo: '',
            movimientos: 0,
            clics: 0,
            botones: [],
            rueda: 0
        };
        let perfUltimoMovimiento = 0;

        const DIAGUSB = (document.body && document.body.dataset) ? document.body.dataset : {};

        const DIAGUSB_CLIENT_ID = (() => {
            try {
                if (window.crypto && crypto.randomUUID) return crypto.randomUUID();
            } catch (e) {}
            return 'c' + Date.now().toString(36) + Math.random().toString(36).slice(2);
        })();

        function latidoDiagUSB() {
            fetch('/api/latido', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({id: DIAGUSB_CLIENT_ID}),
                keepalive: true
            }).catch(() => {});
        }

        function despedidaDiagUSB() {
            try {
                const cuerpo = JSON.stringify({id: DIAGUSB_CLIENT_ID});
                if (navigator.sendBeacon) {
                    navigator.sendBeacon('/api/despedida',
                        new Blob([cuerpo], {type: 'application/json'}));
                }
            } catch (e) {}
        }

        function escHtml(s) {
            const d = document.createElement('div');
            d.textContent = s == null ? '' : String(s);
            return d.innerHTML;
        }

        function setTexto(id, valor) {
            const el = document.getElementById(id);
            if (el) el.textContent = valor;
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
            pruebaPerifericos.activa = false;
            document.getElementById('accionesSection').style.display = 'none';
            document.getElementById('btnWord').style.display = 'none';
            document.getElementById('btnPdf').style.display = 'none';
            document.getElementById('btnSnapAntes').style.display = 'none';
            document.getElementById('btnSnapCompara').style.display = 'none';
            document.getElementById('diffSection').style.display = 'none';
            document.getElementById('referenciaSection').style.display = 'none';
            document.getElementById('referenciaTabla').innerHTML = '';
            const entregaSec = document.getElementById('entregaSection');
            if (entregaSec) entregaSec.style.display = 'none';
            const entregaRes = document.getElementById('entregaResultado');
            if (entregaRes) entregaRes.textContent = 'Sin entregas en esta sesión.';
            const consent = document.getElementById('entregaConsentimiento');
            if (consent) consent.checked = false;
            const perif = document.getElementById('perifericosSection');
            if (perif) perif.style.display = 'none';
            const resultadoPerif = document.getElementById('perifericosResultado');
            if (resultadoPerif) resultadoPerif.innerHTML = '';
        }

        function renderProblemas(findings) {
            const section = document.getElementById('accionesSection');
            const titulo = document.getElementById('accionesTitulo');
            const lista = document.getElementById('problemasLista');
            const mejorasLista = document.getElementById('mejorasLista');
            const colores = {critical: '#C53030', error: '#C05621', warning: '#B7791F', ok: '#157F45'};
            const sevLabel = {critical: 'CRÍTICO', error: 'ERROR', warning: 'ADVERTENCIA', ok: 'OK'};
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

            const mejoras = (currentDiag && currentDiag.improvements) || [];
            if (mejoras.length === 0) {
                mejorasLista.innerHTML = '';
            } else {
                let mh = '<div class="mejoras-title">Mejoras sugeridas (marque las que implementó):</div>';
                mejoras.forEach((m, i) => {
                    mh += '<div class="problema-item" style="border-left-color:#22B8F0;">';
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
            document.getElementById('referenciaSection').style.display = 'block';
            renderReferencia(currentDiag && currentDiag.referencia);
            const seccionEntrega = document.getElementById('entregaSection');
            if (seccionEntrega) seccionEntrega.style.display = 'block';
            const esPerifericos = !!(currentDiag && currentDiag.package === 'perifericos');
            const seccionPerif = document.getElementById('perifericosSection');
            if (seccionPerif) seccionPerif.style.display = esPerifericos ? 'block' : 'none';
            if (esPerifericos) {
                if (!currentDiag.prueba_perifericos) reiniciarEstadoPruebaPerif();
                renderPruebaPerif();
            }
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
                comparacion_forzada: !!lastComparacionForzada,
                metricas_base: lastMetricasBase,
                metricas_actual: lastMetricasActual
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

        function publicarPruebaPerif() {
            if (!currentDiag) return;
            currentDiag.prueba_perifericos = {
                prueba_ejecutada: pruebaPerifericos.prueba_ejecutada,
                iniciada_en: pruebaPerifericos.iniciada_en,
                finalizada_en: pruebaPerifericos.finalizada_en,
                teclas: pruebaPerifericos.teclas,
                ultima_tecla: pruebaPerifericos.ultima_tecla,
                ultimo_codigo: pruebaPerifericos.ultimo_codigo,
                movimientos: pruebaPerifericos.movimientos,
                clics: pruebaPerifericos.clics,
                botones: pruebaPerifericos.botones.slice(),
                rueda: pruebaPerifericos.rueda
            };
        }

        function reiniciarEstadoPruebaPerif() {
            pruebaPerifericos.activa = false;
            pruebaPerifericos.prueba_ejecutada = false;
            pruebaPerifericos.iniciada_en = '';
            pruebaPerifericos.finalizada_en = '';
            pruebaPerifericos.teclas = 0;
            pruebaPerifericos.ultima_tecla = '';
            pruebaPerifericos.ultimo_codigo = '';
            pruebaPerifericos.movimientos = 0;
            pruebaPerifericos.clics = 0;
            pruebaPerifericos.botones = [];
            pruebaPerifericos.rueda = 0;
            perfUltimoMovimiento = 0;
            if (currentDiag) delete currentDiag.prueba_perifericos;
        }

        function renderPruebaPerif() {
            const panel = document.getElementById('perifericosPanel');
            const estado = document.getElementById('perifericosEstado');
            const resultado = document.getElementById('perifericosResultado');
            if (!panel || !estado || !resultado) return;
            panel.classList.toggle('activa', pruebaPerifericos.activa);
            if (pruebaPerifericos.activa) {
                estado.textContent = 'Prueba en curso: use el teclado y el mouse dentro del recuadro. Escape la detiene.';
            } else if (pruebaPerifericos.prueba_ejecutada) {
                estado.textContent = 'Prueba detenida. Los eventos recibidos quedan en el informe.';
            } else {
                estado.textContent = 'Prueba no iniciada.';
            }
            if (!pruebaPerifericos.prueba_ejecutada) {
                resultado.innerHTML = '';
                return;
            }
            const nombres = {0: 'Izquierdo', 1: 'Medio', 2: 'Derecho'};
            const botones = pruebaPerifericos.botones
                .map(b => nombres[b] || ('Botón ' + b)).join(', ') || 'ninguno';
            const inicio = (pruebaPerifericos.iniciada_en || '').slice(0, 19).replace('T', ' ');
            const fin = (pruebaPerifericos.finalizada_en || '').slice(0, 19).replace('T', ' ');
            let html = '<table class="diff-table"><tr><th>Prueba</th><th>Resultado</th></tr>';
            html += '<tr><td>Teclas recibidas</td><td>' + pruebaPerifericos.teclas +
                (pruebaPerifericos.ultima_tecla
                    ? ' (última: ' + escHtml(pruebaPerifericos.ultima_tecla) +
                      ', código ' + escHtml(pruebaPerifericos.ultimo_codigo || '-') + ')'
                    : '') + '</td></tr>';
            html += '<tr><td>Movimientos del puntero</td><td>' + pruebaPerifericos.movimientos + '</td></tr>';
            html += '<tr><td>Clics</td><td>' + pruebaPerifericos.clics + ' (' + escHtml(botones) + ')</td></tr>';
            html += '<tr><td>Rueda</td><td>' + pruebaPerifericos.rueda + '</td></tr>';
            html += '<tr><td>Inicio / fin</td><td>' + escHtml(inicio || '-') + ' / ' + escHtml(fin || 'en curso') + '</td></tr>';
            html += '</table>';
            if (!pruebaPerifericos.teclas && !pruebaPerifericos.movimientos &&
                !pruebaPerifericos.clics && !pruebaPerifericos.rueda) {
                html += '<div class="diff-sin-cambios">No se recibieron eventos de teclado ni de puntero durante la prueba.</div>';
            }
            resultado.innerHTML = html;
        }

        function iniciarPruebaPerifericos() {
            if (!currentDiag || currentDiag.package !== 'perifericos') {
                alert('Ejecute primero el diagnóstico del módulo Periféricos.');
                return;
            }
            reiniciarEstadoPruebaPerif();
            pruebaPerifericos.activa = true;
            pruebaPerifericos.prueba_ejecutada = true;
            pruebaPerifericos.iniciada_en = new Date().toISOString();
            const panel = document.getElementById('perifericosPanel');
            if (panel) {
                panel.textContent = 'Prueba activa: presione teclas, mueva el mouse, haga clic y use la rueda. Escape detiene la prueba.';
                panel.focus();
            }
            publicarPruebaPerif();
            renderPruebaPerif();
        }

        function detenerPruebaPerifericos() {
            if (!pruebaPerifericos.prueba_ejecutada) return;
            pruebaPerifericos.activa = false;
            if (!pruebaPerifericos.finalizada_en) {
                pruebaPerifericos.finalizada_en = new Date().toISOString();
            }
            const panel = document.getElementById('perifericosPanel');
            if (panel) panel.textContent = 'Prueba detenida. Puede iniciarla de nuevo o usar el resultado en el informe.';
            publicarPruebaPerif();
            renderPruebaPerif();
        }

        function limpiarPruebaPerifericos() {
            reiniciarEstadoPruebaPerif();
            const panel = document.getElementById('perifericosPanel');
            if (panel) panel.textContent = 'Pulse «Iniciar prueba» y luego use el teclado y el mouse dentro de este recuadro.';
            renderPruebaPerif();
        }

        function conectarPruebaPerifericos() {
            const panel = document.getElementById('perifericosPanel');
            if (!panel) return;
            panel.addEventListener('keydown', ev => {
                if (!pruebaPerifericos.activa) return;
                if (ev.key === 'Escape') {
                    ev.preventDefault();
                    detenerPruebaPerifericos();
                    return;
                }
                ev.preventDefault();
                pruebaPerifericos.teclas += 1;
                pruebaPerifericos.ultima_tecla = String(ev.key || '').slice(0, 24);
                pruebaPerifericos.ultimo_codigo = String(ev.code || '').slice(0, 32);
                publicarPruebaPerif();
                renderPruebaPerif();
            });
            panel.addEventListener('mousemove', () => {
                if (!pruebaPerifericos.activa) return;
                const ahora = Date.now();
                if (ahora - perfUltimoMovimiento < 120) return;
                perfUltimoMovimiento = ahora;
                pruebaPerifericos.movimientos += 1;
                publicarPruebaPerif();
                renderPruebaPerif();
            });
            panel.addEventListener('mousedown', ev => {
                if (!pruebaPerifericos.activa) return;
                ev.preventDefault();
                pruebaPerifericos.clics += 1;
                if (!pruebaPerifericos.botones.includes(ev.button)) {
                    pruebaPerifericos.botones.push(ev.button);
                }
                publicarPruebaPerif();
                renderPruebaPerif();
            });
            panel.addEventListener('wheel', ev => {
                if (!pruebaPerifericos.activa) return;
                ev.preventDefault();
                pruebaPerifericos.rueda += (ev.deltaY > 0 ? 1 : (ev.deltaY < 0 ? -1 : 0));
                publicarPruebaPerif();
                renderPruebaPerif();
            }, {passive: false});
            panel.addEventListener('contextmenu', ev => {
                if (pruebaPerifericos.activa) ev.preventDefault();
            });
        }

        // ---------------- Entrega opcional del informe ----------------
        let entregaEstado = null;

        function ponerValor(id, valor) {
            const el = document.getElementById(id);
            if (el) el.value = valor == null ? '' : valor;
        }

        function leerValor(id) {
            const el = document.getElementById(id);
            return el ? el.value : '';
        }

        function marcar(id, activo) {
            const el = document.getElementById(id);
            if (el) el.checked = !!activo;
        }

        function leerMarcado(id) {
            const el = document.getElementById(id);
            return !!(el && el.checked);
        }

        function renderHistorialEntregas(entregas) {
            const cont = document.getElementById('entregaHistorial');
            if (!cont) return;
            if (!entregas || !entregas.length) {
                cont.innerHTML = '<p class="acciones-hint">Todavía no se envió ningún informe ni se guardó ninguna copia.</p>';
                return;
            }
            let html = '<h4 style="margin-top:14px;">Últimas entregas</h4><table class="diff-table"><tr><th>Fecha</th><th>Tipo</th><th>Destino</th><th>Resultado</th></tr>';
            entregas.slice(0, 8).forEach(e => {
                const destino = (e.destinatarios && e.destinatarios.length)
                    ? e.destinatarios.join(', ')
                    : (e.destino || '');
                html += '<tr><td>' + escHtml((e.fecha || '').replace('T', ' ')) + '</td>';
                html += '<td>' + escHtml(e.tipo || '') + '</td>';
                html += '<td>' + escHtml(destino) + '</td>';
                html += '<td>' + (e.ok ? 'Enviado' : 'Falló: ' + escHtml(e.detalle || '')) + '</td></tr>';
            });
            html += '</table>';
            cont.innerHTML = html;
        }

        function actualizarEstadoEntrega() {
            if (!entregaEstado) return;
            const cfg = entregaEstado.config || {};
            const correo = cfg.correo || {};
            const copia = cfg.copia || {};
            let texto = correo.habilitado
                ? ('Correo habilitado: ' + (correo.servidor || 'sin servidor') + ':' + (correo.puerto || '') +
                   ' (' + (correo.seguridad || '') + ') · ' + ((correo.destinatarios || []).length) + ' destinatario(s).')
                : 'Correo deshabilitado.';
            if (correo.usuario) {
                texto += entregaEstado.secreto_guardado
                    ? ' Contraseña guardada cifrada con Windows.'
                    : ' Contraseña no guardada: se pedirá en cada envío.';
            }
            texto += copia.habilitada
                ? ' Copia habilitada en: ' + (copia.destino || '(sin carpeta)') + '.'
                : ' Copia deshabilitada.';
            if (!entregaEstado.dpapi_disponible) {
                texto += ' Este sistema no ofrece DPAPI: la contraseña solo se usa en memoria.';
            }
            setTexto('entregaEstadoCorreo', texto);
            renderHistorialEntregas(entregaEstado.entregas || []);
        }

        async function cargarLiveUSB() {
            const cont = document.getElementById('liveUsbLista');
            const est = document.getElementById('liveUsbEstado');
            if (!cont || !est) return;
            try {
                const r = await fetch('/api/live-usb');
                const d = await r.json();
                if (d.error) throw new Error(d.error);
                const total = d.verificadas || 0;
                const listas = d.listas || 0;
                const excluidas = d.excluidas || 0;
                est.className = 'config-estado ' + (d.todo_verificado ? 'ok' : 'warn');
                est.textContent = (d.todo_verificado
                    ? 'Manifiesto completo: '
                    : 'Manifiesto incompleto: ') + listas + ' de ' + total +
                    ' imágenes con datos oficiales; ' + excluidas +
                    ' excluidas y documentadas.';
                let html = '<table class="diff-table"><thead><tr>' +
                    '<th>Herramienta</th><th>Estado</th><th>Versión</th>' +
                    '<th>Licencia</th><th>Detalle</th></tr></thead><tbody>';
                (d.herramientas || []).forEach(h => {
                    const excluida = h.estado === 'excluido';
                    const etiqueta = excluida ? 'Excluida' : (h.lista ? 'Verificada' : 'Pendiente');
                    const insignia = excluida
                        ? '<span class="muted">Excluida</span>'
                        : '<span class="diag-badge ' + (h.lista ? 'ok' : 'warning') + '">' + etiqueta + '</span>';
                    const detalle = excluida
                        ? (h.motivo || 'sin motivo')
                        : ((h.motivos || []).join('; ') || h.archivo || '');
                    html += '<tr><td><b>' + escHtml(h.nombre) + '</b></td>' +
                        '<td>' + insignia + '</td>' +
                        '<td>' + escHtml(h.version || '—') + '</td>' +
                        '<td>' + escHtml(h.licencia || '—') + '</td>' +
                        '<td>' + escHtml(detalle) + '</td></tr>';
                });
                html += '</tbody></table>';
                cont.innerHTML = html;
            } catch (e) {
                est.className = 'config-estado warn';
                est.textContent = 'No se pudo leer el manifiesto de live USB: ' + e.message;
                cont.innerHTML = '';
            }
        }

        async function cargarEntrega() {            try {
                const r = await fetch('/api/entrega');
                const data = await r.json();
                if (data.error) throw new Error(data.error);
                entregaEstado = data;
                const correo = (data.config && data.config.correo) || {};
                const copia = (data.config && data.config.copia) || {};
                marcar('entregaCorreoHabilitado', correo.habilitado);
                ponerValor('entregaServidor', correo.servidor);
                ponerValor('entregaPuerto', correo.puerto || 587);
                ponerValor('entregaSeguridad', correo.seguridad || 'starttls');
                ponerValor('entregaUsuario', correo.usuario);
                ponerValor('entregaRemitente', correo.remitente);
                ponerValor('entregaDestinatarios', (correo.destinatarios || []).join('; '));
                ponerValor('entregaAsunto', correo.asunto || 'Informe DiagUSB');
                marcar('entregaCopiaHabilitada', copia.habilitada);
                ponerValor('entregaCopiaDestino', copia.destino);
                const clave = document.getElementById('entregaClave');
                if (clave) clave.value = '';
                actualizarEstadoEntrega();
            } catch (e) {
                setTexto('entregaEstadoCorreo', 'No se pudo leer la configuración de entrega: ' + e.message);
            }
        }

        function configEntregaDesdeFormulario() {
            return {
                correo: {
                    habilitado: leerMarcado('entregaCorreoHabilitado'),
                    servidor: leerValor('entregaServidor').trim(),
                    puerto: Number(leerValor('entregaPuerto')) || 587,
                    seguridad: leerValor('entregaSeguridad') || 'starttls',
                    usuario: leerValor('entregaUsuario').trim(),
                    remitente: leerValor('entregaRemitente').trim(),
                    destinatarios: leerValor('entregaDestinatarios'),
                    asunto: leerValor('entregaAsunto').trim() || 'Informe DiagUSB'
                },
                copia: {
                    habilitada: leerMarcado('entregaCopiaHabilitada'),
                    destino: leerValor('entregaCopiaDestino').trim()
                }
            };
        }

        async function guardarEntregaConfig() {
            setTexto('entregaEstadoCorreo', 'Guardando configuración…');
            try {
                const r = await fetch('/api/entrega/config', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify(configEntregaDesdeFormulario())
                });
                const data = await r.json();
                if (data.error) throw new Error(data.error);
                entregaEstado = data.estado || entregaEstado;
                actualizarEstadoEntrega();
                const detalle = (document.getElementById('entregaEstadoCorreo') || {}).textContent || '';
                setTexto('entregaEstadoCorreo', 'Configuración guardada. ' + detalle);
            } catch (e) {
                setTexto('entregaEstadoCorreo', 'No se guardó: ' + e.message);
            }
        }

        async function guardarSecretoEntrega() {
            const clave = leerValor('entregaClave');
            if (!clave) return false;
            const r = await fetch('/api/entrega/secreto', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({clave: clave})
            });
            const data = await r.json();
            if (data.error) throw new Error(data.error);
            const campo = document.getElementById('entregaClave');
            if (campo) campo.value = '';
            return true;
        }

        async function probarEntrega() {
            setTexto('entregaEstadoCorreo', 'Probando la conexión con el servidor…');
            try {
                // Guarda primero lo que el técnico escribió en el formulario.
                await guardarEntregaConfig();
                if (leerMarcado('entregaRecordar') && leerValor('entregaClave')) {
                    await guardarSecretoEntrega();
                }
                const r = await fetch('/api/entrega/probar', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({clave: leerValor('entregaClave')})
                });
                const data = await r.json();
                if (data.error) throw new Error(data.error);
                setTexto('entregaEstadoCorreo', 'Conexión correcta con ' + data.servidor +
                    ':' + data.puerto + (data.autenticado ? ' (sesión iniciada).' : ' (sin autenticación).'));
                await cargarEntrega();
            } catch (e) {
                setTexto('entregaEstadoCorreo', 'Falló la prueba: ' + e.message);
            }
        }

        async function olvidarClaveEntrega() {
            try {
                const r = await fetch('/api/entrega/secreto', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({olvidar: true})
                });
                const data = await r.json();
                if (data.error) throw new Error(data.error);
                await cargarEntrega();
            } catch (e) {
                setTexto('entregaEstadoCorreo', 'No se pudo olvidar la contraseña: ' + e.message);
            }
        }

        async function enviarEntrega(ruta, cuerpo) {
            const r = await fetch(ruta, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(cuerpo)
            });
            const data = await r.json();
            if (data.error) throw new Error(data.error);
            return data;
        }

        async function prepararCuerpoEntrega() {
            if (!currentDiag) {
                alert('Ejecute primero un diagnóstico.');
                return null;
            }
            if (!leerMarcado('entregaConsentimiento')) {
                alert('Marque la casilla de consentimiento para entregar el informe.');
                return null;
            }
            const cuerpo = collectPayload();
            cuerpo.consentimiento = true;
            cuerpo.formatos = ['pdf', 'html', 'json'];
            if (leerMarcado('entregaRecordar') && leerValor('entregaClave')) {
                await guardarSecretoEntrega();
            }
            cuerpo.clave = leerValor('entregaClave');
            return cuerpo;
        }

        async function enviarInformeEntrega() {
            setTexto('entregaResultado', 'Generando y enviando el informe…');
            try {
                const cuerpo = await prepararCuerpoEntrega();
                if (!cuerpo) { setTexto('entregaResultado', 'Envío cancelado.'); return; }
                const data = await enviarEntrega('/api/entrega/enviar', cuerpo);
                setTexto('entregaResultado', 'Informe enviado a ' +
                    (data.destinatarios || []).join(', ') + ' (' + data.adjuntos.length + ' adjuntos, ' +
                    Math.round((data.bytes || 0) / 1024) + ' KB).');
                const campo = document.getElementById('entregaClave');
                if (campo) campo.value = '';
                await cargarEntrega();
            } catch (e) {
                setTexto('entregaResultado', 'No se envió: ' + e.message);
            }
        }

        async function guardarCopiaEntrega() {
            setTexto('entregaResultado', 'Generando la copia…');
            try {
                const cuerpo = await prepararCuerpoEntrega();
                if (!cuerpo) { setTexto('entregaResultado', 'Copia cancelada.'); return; }
                cuerpo.destino = leerValor('entregaCopiaDestino').trim();
                const data = await enviarEntrega('/api/entrega/copia', cuerpo);
                setTexto('entregaResultado', 'Copia guardada: ' + data.archivo);
                await cargarEntrega();
            } catch (e) {
                setTexto('entregaResultado', 'No se guardó la copia: ' + e.message);
            }
        }

        function irAConfigEntrega() {
            mostrarVista('configuracion');
            const panel = document.getElementById('entregaEstadoCorreo');
            if (panel && panel.scrollIntoView) panel.scrollIntoView({behavior: 'smooth', block: 'center'});
            cargarEntrega();
        }

        function renderReferencia(ref) {
            const estadoEl = document.getElementById('referenciaEstado');
            const tabla = document.getElementById('referenciaTabla');
            if (!estadoEl || !tabla) return;
            const e = (ref && ref.estado) || null;
            if (!ref) {
                estadoEl.textContent = 'Consultando referencia del equipo...';
                tabla.innerHTML = '';
                return;
            }
            if (e && e.disponible) {
                estadoEl.innerHTML = '<b>Referencia disponible</b> &middot; capturada el ' +
                    escHtml((e.capturada_en || '').slice(0, 19).replace('T', ' ')) +
                    ' &middot; ' + escHtml(e.colectores || 0) + ' colector(es)';
            } else {
                estadoEl.innerHTML = '<b>Sin referencia guardada</b> &middot; guarde una captura cuando el equipo funcione bien.';
            }
            if (!ref.disponible) {
                tabla.innerHTML = '';
                return;
            }
            const diffs = ref.diferencias || [];
            let html = '<div class="acciones-hint">' + escHtml(ref.mensaje || '') + '</div>';
            if (!diffs.length) {
                html += '<div class="diff-sin-cambios">Sin diferencias respecto de la referencia.</div>';
            } else {
                html += '<table class="diff-table"><tr><th>Severidad</th><th>Colector</th><th>Qué cambió</th><th>Antes</th><th>Ahora</th></tr>';
                diffs.forEach(d => {
                    const fmt = v => {
                        if (v && typeof v === 'object') return '[' + (Array.isArray(v) ? v.length + ' registros' : Object.keys(v).length + ' campos') + ']';
                        return v == null ? '-' : String(v);
                    };
                    html += '<tr><td>' + escHtml(d.severidad || '') + '</td><td>' + escHtml(d.collector_id || '') +
                        '</td><td>' + escHtml(d.mensaje || '') + '</td><td>' + escHtml(fmt(d.antes)) +
                        '</td><td>' + escHtml(fmt(d.ahora)) + '</td></tr>';
                });
                html += '</table>';
            }
            tabla.innerHTML = html;
        }

        async function cargarReferencia() {
            try {
                const r = await fetch('/api/referencia', {cache: 'no-store'});
                const d = await r.json();
                if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
                const estadoEl = document.getElementById('referenciaEstado');
                const tabla = document.getElementById('referenciaTabla');
                if (estadoEl && tabla) renderReferencia({disponible: false, estado: d});
            } catch (e) {
                const estadoEl = document.getElementById('referenciaEstado');
                if (estadoEl) estadoEl.textContent = 'No se pudo consultar la referencia del equipo.';
            }
        }

        async function guardarReferencia() {
            if (!currentDiag) {
                alert('Ejecute primero un diagnóstico.');
                return;
            }
            const btn = document.getElementById('btnReferenciaGuardar');
            if (btn) btn.disabled = true;
            setStatus('running', 'Guardando referencia del equipo...');
            try {
                const resp = await fetch('/api/referencia', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({accion: 'guardar', results: currentDiag.results || []})
                });
                const d = await resp.json();
                if (!resp.ok) throw new Error(d.error || ('HTTP ' + resp.status));
                renderReferencia({disponible: false, estado: d.estado});
                setStatus('ready', 'Referencia guardada para este equipo.');
            } catch (e) {
                setStatus('error', 'Error al guardar la referencia: ' + e.message);
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        async function compararReferencia() {
            if (!currentDiag) {
                alert('Ejecute primero un diagnóstico.');
                return;
            }
            const btn = document.getElementById('btnReferenciaComparar');
            if (btn) btn.disabled = true;
            setStatus('running', 'Comparando contra la referencia del equipo...');
            try {
                const resp = await fetch('/api/referencia', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({accion: 'comparar', results: currentDiag.results || []})
                });
                const d = await resp.json();
                if (!resp.ok) throw new Error(d.error || ('HTTP ' + resp.status));
                renderReferencia(d);
                currentDiag.referencia = d;
                setStatus('ready', d.mensaje || 'Comparación con la referencia completada.');
            } catch (e) {
                setStatus('error', 'Error al comparar la referencia: ' + e.message);
            } finally {
                if (btn) btn.disabled = false;
            }
        }

        function renderDiff(diffs, baselineEn) {
            const sec = document.getElementById('diffSection');
            const el = document.getElementById('diffTabla');
            lastDiffs = diffs || [];
            let html = '<div class="acciones-hint">Snapshot de referencia: ' + escHtml(baselineEn || '-') + '</div>';
            if (!lastDiffs.length) {
                html += '<div class="diff-sin-cambios">Sin cambios entre el estado ANTES y el actual.</div>';
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
                if (d.metricas_base && d.metricas_actual) {
                    lastMetricasBase = d.metricas_base;
                    lastMetricasActual = d.metricas_actual;
                    renderMetricas(d.metricas_actual);
                }
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

        const NOMBRES_PAQUETE = {
            impresion: 'Impresión',
            redes: 'Adaptadores de Red',
            conectividad: 'Conectividad',
            wifi: 'WiFi',
            disco: 'Disco',
            memoria: 'Memoria',
            temperatura: 'Temperatura CPU',
            bateria: 'Batería',
            servicios: 'Servicios',
            seguridad: 'Seguridad',
            windows_update: 'Windows Update',
            drivers: 'Drivers',
            eventos: 'Eventos Críticos',
            contexto: 'Contexto Sistema',
            inventario_general: 'Inventario General'
        };

        function nombrePaquete(id) {
            return NOMBRES_PAQUETE[id] || String(id || '').replace(/_/g, ' ');
        }

        function aplicarCapacidades(caps) {
            capacidadesActuales = caps || null;
            const resumen = document.getElementById('capacidadesResumen');
            if (resumen) {
                if (!caps) {
                    resumen.textContent = 'Detección de hardware no disponible';
                } else if (!caps.ok) {
                    resumen.textContent = caps.error || 'Detección de hardware no disponible';
                } else {
                    resumen.textContent = caps.resumen || '';
                }
            }
            const paquetes = (caps && caps.paquetes) || [];
            document.querySelectorAll('.mod-btn[data-paquete]').forEach(btn => {
                const id = btn.getAttribute('data-paquete');
                const info = paquetes.find(p => p.id === id);
                const motivo = btn.querySelector('.mod-motivo');
                const noAplica = !!(info && info.available === false);
                btn.disabled = noAplica || isRunning;
                btn.classList.toggle('no-aplica', noAplica);
                let texto = '';
                if (info) {
                    texto = info.reason || (info.available ? 'Disponible' : 'No aplica');
                    if (noAplica) texto = 'No aplica: ' + texto;
                }
                if (motivo) {
                    motivo.textContent = texto;
                    motivo.classList.toggle('con-advertencia', !!(info && info.warning));
                }
                btn.title = nombrePaquete(id) + (texto ? ': ' + texto : '');
                btn.setAttribute('aria-label', btn.title);
            });
        }

        function setBotonesOcupados(ocupado) {
            const botones = document.querySelectorAll('.mod-btn:not(#btnKb):not(#btnRegistro)');
            const actualizar = document.getElementById('btnActualizarCapacidades');
            if (actualizar) actualizar.disabled = ocupado;
            if (ocupado) {
                botones.forEach(b => { b.disabled = true; });
                return;
            }
            botones.forEach(b => {
                if (!b.hasAttribute('data-paquete')) b.disabled = false;
            });
            aplicarCapacidades(capacidadesActuales);
        }

        async function cargarCapacidades(forzar) {
            const boton = document.getElementById('btnActualizarCapacidades');
            if (boton) boton.disabled = true;
            const resumen = document.getElementById('capacidadesResumen');
            if (resumen && !capacidadesActuales) {
                resumen.textContent = 'Detectando hardware y conexiones…';
            }
            try {
                const url = '/api/capacidades' + (forzar ? '?force=1' : '');
                const r = await fetch(url, {cache: 'no-store'});
                const data = await r.json();
                aplicarCapacidades(data);
            } catch (e) {
                if (resumen) resumen.textContent = 'No se pudo detectar el hardware';
            } finally {
                if (boton) boton.disabled = isRunning;
            }
        }

        function nombreColector(id) {
            return String(id || '').replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
        }

        function segundosLegibles(valor) {
            const s = Math.max(0, Math.round(Number(valor) || 0));
            if (s < 60) return s + ' s';
            const m = Math.floor(s / 60);
            return m + ' min ' + (s % 60) + ' s';
        }

        let progresoTimer = null;
        let progresoConsultando = false;

        function detenerProgreso() {
            if (progresoTimer) {
                clearInterval(progresoTimer);
                progresoTimer = null;
            }
            progresoConsultando = false;
        }

        function mostrarProgreso(titulo, modo) {
            document.getElementById('resultsContent').innerHTML =
                '<div class="progreso-panel" id="progresoPanel">' +
                    '<div class="progreso-cabecera">' +
                        '<div class="progreso-anillo" id="progresoAnillo" style="--pct:0%">' +
                            '<div class="progreso-anillo-centro"><span id="progresoAnilloPct">0%</span></div>' +
                        '</div>' +
                        '<div class="progreso-texto">' +
                            '<span class="progreso-eyebrow">ANÁLISIS EN CURSO</span>' +
                            '<h3 class="progreso-titulo" id="progresoTitulo"></h3>' +
                            '<p class="progreso-detalle" id="progresoDetalle">Preparando colectores…</p>' +
                        '</div>' +
                    '</div>' +
                    '<div class="progreso-barra activa"><span id="progresoBarra" style="width:0%"></span></div>' +
                    '<div class="progreso-meta">' +
                        '<span id="progresoCuenta">0 de 0 colectores</span>' +
                        '<span id="progresoTiempo">0 s</span>' +
                    '</div>' +
                    '<div class="progreso-paquetes" id="progresoPaquetes"></div>' +
                    '<p class="progreso-hint">El análisis se ejecuta en segundo plano. No se abrirán ventanas de consola.</p>' +
                '</div>';
            const tituloEl = document.getElementById('progresoTitulo');
            if (tituloEl) tituloEl.textContent = titulo;
            const paquetesEl = document.getElementById('progresoPaquetes');
            if (paquetesEl && modo !== 'full') paquetesEl.style.display = 'none';
        }

        function renderProgreso(p) {
            if (!p || !document.getElementById('progresoPanel')) return;
            const pct = Math.max(0, Math.min(100, Number(p.porcentaje) || 0));
            const anillo = document.getElementById('progresoAnillo');
            const barra = document.getElementById('progresoBarra');
            const pctEl = document.getElementById('progresoAnilloPct');
            const cuenta = document.getElementById('progresoCuenta');
            const tiempo = document.getElementById('progresoTiempo');
            const detalle = document.getElementById('progresoDetalle');
            if (anillo) anillo.style.setProperty('--pct', pct + '%');
            if (barra) barra.style.width = pct + '%';
            if (pctEl) pctEl.textContent = Math.round(pct) + '%';
            if (cuenta) {
                cuenta.textContent = p.total ? (p.completados + ' de ' + p.total + ' colectores')
                                             : 'Preparando colectores…';
            }
            if (tiempo) {
                let texto = segundosLegibles(p.transcurrido);
                if (p.restante !== null && p.restante !== undefined) {
                    texto += ' · ~' + segundosLegibles(p.restante) + ' restantes';
                }
                tiempo.textContent = texto;
            }
            if (detalle) {
                const activos = (p.paquetes || []).filter(x => x.estado === 'ejecutando');
                if (p.actual) {
                    detalle.textContent = 'Ejecutando ' + nombreColector(p.actual) + '…';
                } else if (activos.length > 1) {
                    detalle.textContent = activos.length + ' módulos en paralelo…';
                } else if (p.activo) {
                    detalle.textContent = 'Preparando el siguiente colector…';
                } else {
                    detalle.textContent = 'Finalizando el análisis…';
                }
            }
            const contPaquetes = document.getElementById('progresoPaquetes');
            if (contPaquetes && p.modo === 'full' && (p.paquetes || []).length) {
                contPaquetes.style.display = '';
                contPaquetes.innerHTML = p.paquetes.map(paquete => {
                    const ppct = Math.max(0, Math.min(100, Number(paquete.porcentaje) || 0));
                    const estado = paquete.estado || 'pendiente';
                    return '<div class="progreso-paquete ' + estado + '">' +
                        '<div class="progreso-paquete-top">' +
                            '<span class="progreso-paquete-nombre">' + escHtml(paquete.label) + '</span>' +
                            '<span class="progreso-paquete-cuenta">' + paquete.completados + '/' + paquete.total + '</span>' +
                        '</div>' +
                        '<div class="progreso-mini"><span style="width:' + ppct + '%"></span></div>' +
                    '</div>';
                }).join('');
            }
        }

        function iniciarProgreso(titulo, modo) {
            detenerProgreso();
            mostrarProgreso(titulo, modo);
            const consultar = async () => {
                if (progresoConsultando) return;
                progresoConsultando = true;
                try {
                    const r = await fetch('/api/progreso', {cache: 'no-store'});
                    if (r.ok) renderProgreso(await r.json());
                } catch (e) {
                } finally {
                    progresoConsultando = false;
                }
            };
            consultar();
            progresoTimer = setInterval(consultar, 650);
        }

        function formatJson(data) {
            try {
                return JSON.stringify(data, null, 2);
            } catch (e) {
                return String(data);
            }
        }

        function estadoEtiqueta(status) {
            const etiquetas = {
                ok: 'ok',
                empty: 'sin datos',
                error: 'error',
                timeout: 'tiempo agotado',
                not_available: 'no disponible',
                denied: 'requiere administrador'
            };
            return etiquetas[status] || status;
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
            mostrarVista('diagnosticos');

            setBotonesOcupados(true);

            setStatus('running', 'Ejecutando diagnóstico de ' + package + '...');
            iniciarProgreso(nombrePaquete(package), 'paquete');

            try {
                const response = await fetch('/api/diagnose?package=' + encodeURIComponent(package));
                const data = await response.json();

                if (data.error) {
                    detenerProgreso();
                    hideAcciones();
                    mostrarIntegridad([]);
                    document.getElementById('resultsContent').innerHTML = '<div class="diag-card error"><p>' + escHtml(data.error) + '</p></div>';
                    if (data.unavailable) {
                        setStatus('error', 'No aplica: ' + (data.reason || data.error));
                        cargarCapacidades(true);
                    } else {
                        setStatus('error', 'Error: ' + data.error);
                    }
                } else {
                    detenerProgreso();
                    currentDiag = data;
                    lastDiffs = null;
                    lastComparacionForzada = false;
                    lastMetricasBase = null;
                    lastMetricasActual = null;
                    mostrarIntegridad(data.integridad_fallida);
                    document.getElementById('diffSection').style.display = 'none';
                    const nProblemas = (data.findings || []).length;
                    const noEval = (data.not_available_count || 0) + (data.denied_count || 0);
                    renderProblemas(data.findings || []);
                    renderMetricas(data.metricas);
                    let html = '<div class="diag-card ' + ((data.error_count > 0 || nProblemas > 0) ? 'warning' : 'success') + '">';
                    html += '<div class="diag-header">';
                    html += '<span class="diag-title">' + escHtml(data.package_label) + '</span>';
                    html += getStatusBadge(data.ok_count, data.error_count, nProblemas, data.empty_count);
                    html += '</div>';
                    html += '<div class="diag-stats">';
                    html += '<span>Colectores: ' + data.collectors_count + '</span>';
                    html += '<span>OK: ' + data.ok_count + '</span>';
                    html += '<span>Errores: ' + data.error_count + '</span>';
                    html += '<span>Sin datos: ' + (data.empty_count || 0) + '</span>';
                    if (noEval > 0) html += '<span>No evaluado: ' + noEval + '</span>';
                    html += '<span>Problemas: ' + nProblemas + '</span>';
                    html += '<span>' + escHtml(data.timestamp) + '</span>';
                    if (data.identidad && data.identidad.id_corto) html += '<span>Equipo: ' + escHtml(data.identidad.id_corto) + '</span>';
                    html += '</div>';

                    for (const result of data.results) {
                        const status = (result.query && result.query.status) || 'unknown';
                        const cardClass = status === 'ok' ? 'success' : (status === 'error' ? 'error' : 'warning');
                        const badgeClass = status === 'ok' ? 'ok' : (status === 'error' ? 'error' : 'warning');
                        html += '<div class="diag-card ' + cardClass + '" style="margin-top: 12px; border-left-width: 2px;">';
                        html += '<div class="diag-header">';
                        html += '<span class="diag-title">' + escHtml(result.collector_id || 'unknown') + '</span>';
                        html += '<span class="diag-badge ' + badgeClass + '">' + escHtml(estadoEtiqueta(status)) + '</span>';
                        html += '</div>';
                        if (result.query && result.query.message) {
                            html += '<div class="diag-stats"><span>' + escHtml(result.query.message) + '</span></div>';
                        }
                        html += '<div class="diag-json">' + escHtml(formatJson(result.data || result)) + '</div>';
                        html += '</div>';
                    }

                    html += '</div>';
                    document.getElementById('resultsContent').innerHTML = html;
                    setStatus('ready', 'Diagnóstico completado: ' + data.package_label +
                        (data.registro_id ? ' · guardado en registro' : ''));
                    loadRegistro();
                }
            } catch (e) {
                detenerProgreso();
                hideAcciones();
                document.getElementById('resultsContent').innerHTML = '<div class="diag-card error"><p>Error: ' + escHtml(e.message) + '</p></div>';
                setStatus('error', 'Error de conexión');
            }

            detenerProgreso();
            isRunning = false;
            setBotonesOcupados(false);
        }

        async function runFullScan() {
            if (isRunning) return;
            isRunning = true;
            hideAcciones();
            mostrarVista('diagnosticos');

            setBotonesOcupados(true);

            setStatus('running', 'Ejecutando revisión total del equipo...');
            iniciarProgreso('Revisión Total', 'full');

            try {
                const response = await fetch('/api/full-scan');
                const data = await response.json();

                if (data.error) {
                    detenerProgreso();
                    document.getElementById('resultsContent').innerHTML = '<div class="diag-card error"><p>' + escHtml(data.error) + '</p></div>';
                    setStatus('error', 'Error: ' + data.error);
                    isRunning = false;
                    setBotonesOcupados(false);
                    return;
                }

                const integridadTotal = [];
                (data.diagnostics || []).forEach(dg => (dg.integridad_fallida || []).forEach(x => {
                    if (integridadTotal.indexOf(x) === -1) integridadTotal.push(x);
                }));
                mostrarIntegridad(integridadTotal);

                let html = '';
                let totalErrors = 0;
                let totalOk = 0;
                let totalEmpty = 0;
                let totalNoEval = 0;
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
                    const noEval = (diag.not_available_count || 0) + (diag.denied_count || 0);
                    const problems = (diag.findings || []).length;
                    totalErrors += errors;
                    totalOk += ok;
                    totalEmpty += (diag.empty_count || 0);
                    totalNoEval += noEval;
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
                    html += '<span class="diag-title">' + escHtml(diag.package_label) + '</span>';
                    html += getStatusBadge(ok, errors, problems, diag.empty_count);
                    html += '</div>';
                    html += '<div class="diag-stats">';
                    html += '<span>OK: ' + ok + '</span>';
                    html += '<span>Errores: ' + errors + '</span>';
                    html += '<span>Sin datos: ' + (diag.empty_count || 0) + '</span>';
                    if (noEval > 0) html += '<span>No evaluado: ' + noEval + '</span>';
                    html += '<span>Problemas: ' + problems + '</span>';
                    html += '</div>';

                    for (const result of diag.results) {
                        const status = (result.query && result.query.status) || 'unknown';
                        if (status === 'error') {
                            html += '<div class="diag-json" style="margin-top: 8px; padding: 8px;">';
                            html += '<strong>' + escHtml(result.collector_id || 'unknown') + ':</strong> ' + escHtml(formatJson(result.data || result));
                            html += '</div>';
                        } else if (status !== 'ok' && result.query && result.query.message) {
                            html += '<div class="diag-json" style="margin-top: 8px; padding: 8px;">';
                            html += '<strong>' + escHtml(result.collector_id || 'unknown') + ' (' + escHtml(estadoEtiqueta(status)) + '):</strong> ' + escHtml(result.query.message);
                            html += '</div>';
                        }
                    }

                    html += '</div>';
                }

                const omitidos = data.skipped || [];
                const nOmitidos = omitidos.length;
                let htmlOmitidos = '';
                if (nOmitidos) {
                    htmlOmitidos = '<div class="diag-card warning" style="margin-bottom: 20px;">' +
                        '<div class="diag-header">' +
                        '<span class="diag-title">MÓDULOS OMITIDOS</span>' +
                        '<span class="diag-badge warning">' + nOmitidos + ' no aplica(n)</span>' +
                        '</div>' +
                        '<div class="diag-stats"><span>No se ejecutaron porque el hardware o la conexión no están presentes.</span></div>';
                    omitidos.forEach(o => {
                        htmlOmitidos += '<div class="diag-json" style="margin-top: 8px; padding: 8px;">' +
                            '<strong>' + escHtml(o.package_label || o.package || 'Módulo') + ':</strong> ' +
                            escHtml('No aplica — ' + (o.reason || 'sin hardware detectado')) +
                            '</div>';
                    });
                    htmlOmitidos += '</div>';
                }

                html = '<div class="diag-card ' + ((totalErrors > 0 || totalProblems > 0) ? 'warning' : 'success') + '" style="margin-bottom: 20px;">' +
                    '<div class="diag-header">' +
                    '<span class="diag-title">RESUMEN TOTAL</span>' +
                    getStatusBadge(totalOk, totalErrors, totalProblems, totalEmpty) +
                    '</div>' +
                    '<div class="diag-stats">' +
                    '<span>Paquetes analizados: ' + data.diagnostics.length + '</span>' +
                    (nOmitidos ? '<span>Omitidos: ' + nOmitidos + '</span>' : '') +
                    '<span>Colectores OK: ' + totalOk + '</span>' +
                    '<span>Colectores con error: ' + totalErrors + '</span>' +
                    '<span>Sin datos: ' + totalEmpty + '</span>' +
                    (totalNoEval ? '<span>Colectores no evaluados: ' + totalNoEval + '</span>' : '') +
                    '<span>Problemas detectados: ' + totalProblems + '</span>' +
                    '</div>' +
                    '</div>' + htmlOmitidos + html;

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
                    recommendations: (data.recommendations && data.recommendations.length)
                        ? data.recommendations : allRecommendations,
                    estados_accion: (data.diagnostics[0] || {}).estados_accion,
                    metricas: data.metricas,
                    timestamp: data.timestamp
                };
                renderProblemas(allFindings);
                renderMetricas(data.metricas);
                detenerProgreso();

                document.getElementById('resultsContent').innerHTML = html;
                setStatus('ready', 'Revisión total completada' +
                    (nOmitidos ? ' · ' + nOmitidos + ' módulo(s) omitido(s)' : '') +
                    (data.registro_id ? ' · guardado en registro' : ''));
                loadRegistro();
            } catch (e) {
                detenerProgreso();
                document.getElementById('resultsContent').innerHTML = '<div class="diag-card error"><p>Error: ' + escHtml(e.message) + '</p></div>';
                setStatus('error', 'Error de conexión');
            }

            detenerProgreso();
            isRunning = false;
            setBotonesOcupados(false);
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
                '<div class="results-empty"><span class="results-empty-icon"><svg viewBox="0 0 24 24"><circle cx="11" cy="11" r="7"/><line x1="16.5" y1="16.5" x2="21" y2="21"/></svg></span><p>Elija un módulo para ejecutar un diagnóstico</p></div>';
            setStatus('ready', 'Listo para ejecutar diagnósticos');
        }

        // ---------------------------------------------------------------
        // Navegacion entre vistas
        // ---------------------------------------------------------------
        const TITULOS = {
            inicio: ['Inicio', 'Resumen gráfico del estado del equipo'],
            diagnosticos: ['Diagnósticos', 'Ejecute módulos y revise los resultados'],
            historial: ['Historial', 'Análisis guardados en el registro'],
            configuracion: ['Configuración', 'Permisos y carpetas de datos'],
            acerca: ['Acerca de', 'Información del programa']
        };

        function mostrarVista(nombre) {
            const vistas = document.querySelectorAll('.view');
            vistas.forEach(v => { v.style.display = 'none'; });
            const target = document.getElementById('view' + nombre.charAt(0).toUpperCase() + nombre.slice(1));
            if (target) target.style.display = 'block';
            document.querySelectorAll('#navPrincipal .nav-item').forEach(b => {
                b.classList.toggle('activo', b.getAttribute('data-view') === nombre);
            });
            const t = TITULOS[nombre] || TITULOS.inicio;
            setTexto('viewTitulo', t[0]);
            setTexto('viewSub', t[1]);
        }

        function irARegistro() {
            mostrarVista('historial');
            loadRegistro();
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

        // ---------------------------------------------------------------
        // Graficas (SVG propio, sin librerias externas)
        // ---------------------------------------------------------------
        const COLOR_ETIQUETA = {Bueno: '#157F45', 'Atención': '#B7791F', 'Crítico': '#C53030', 'Datos parciales': '#B7791F', 'Sin datos': '#5D7088'};

        function renderMetricas(m) {
            if (!m) return;
            renderGauge(m);
            renderSeveridad(m);
            renderCategorias(m);
            renderMedidores(m);
        }

        function renderGauge(m) {
            setTexto('gaugeTitulo', m.alcance || 'Puntaje');
            const sub = document.getElementById('gaugeAlcance');
            if (sub) sub.textContent = m.leyenda || '';
            const cuerpo = document.getElementById('gaugeCuerpo');
            const nota = (m.alcance && m.alcance.indexOf('paquete') !== -1)
                ? 'Este puntaje no refleja el estado general del equipo.' : '';
            if (m.puntaje == null) {
                cuerpo.innerHTML = '<p class="sin-datos">Sin datos. No se ejecutaron módulos.</p>';
                return;
            }
            const color = COLOR_ETIQUETA[m.etiqueta] || '#5D7088';
            const r = 78, cx = 100, cy = 100;
            const frac = Math.max(0, Math.min(1, m.puntaje / 100));
            const ang = Math.PI * (1 - frac);
            const ex = cx + r * Math.cos(ang);
            const ey = cy - r * Math.sin(ang);
            const bg = 'M ' + (cx - r) + ' ' + cy + ' A ' + r + ' ' + r + ' 0 0 1 ' + (cx + r) + ' ' + cy;
            const val = 'M ' + (cx - r) + ' ' + cy + ' A ' + r + ' ' + r + ' 0 0 1 ' + ex.toFixed(2) + ' ' + ey.toFixed(2);
            const cobertura = (m.cobertura && m.cobertura.porcentaje != null) ? m.cobertura.porcentaje + '%' : '—';
            const c = m.cobertura || {};
            const evaluados = (c.colectores_evaluados != null)
                ? c.colectores_evaluados
                : ((c.colectores_ok || 0) + (c.colectores_sin_datos || 0));
            cuerpo.innerHTML =
                '<div class="gauge-figura">' +
                  '<svg width="200" height="112" viewBox="0 0 200 112">' +
                    '<path d="' + bg + '" stroke="#E3EAF2" stroke-width="16" fill="none" stroke-linecap="round"/>' +
                    '<path d="' + val + '" stroke="' + color + '" stroke-width="16" fill="none" stroke-linecap="round"/>' +
                  '</svg>' +
                  '<div class="gauge-valor" style="color:' + color + '">' + m.puntaje + '<small>/100</small></div>' +
                '</div>' +
                '<div class="gauge-etiqueta" style="color:' + color + '">' + escHtml(m.etiqueta || '') + '</div>' +
                '<div class="gauge-cobertura">Cobertura: <b>' + cobertura + '</b> (' + evaluados +
                    '/' + (c.colectores_ejecutados || 0) + ' evaluados: ' + (c.colectores_ok || 0) +
                    ' OK + ' + (c.colectores_sin_datos || 0) + ' sin datos)</div>' +
                (nota ? '<div class="gauge-cobertura">' + nota + '</div>' : '');
        }

        function donaSvg(segmentos, totalCentro) {
            const r = 54, cx = 70, cy = 70, grosor = 16;
            const C = 2 * Math.PI * r;
            const suma = segmentos.reduce((a, s) => a + s.valor, 0);
            let offset = 0;
            let partes = '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="#E3EAF2" stroke-width="' + grosor + '"/>';
            if (suma > 0) {
                segmentos.forEach(s => {
                    const len = (s.valor / suma) * C;
                    partes += '<circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="none" stroke="' + s.color +
                        '" stroke-width="' + grosor + '" stroke-dasharray="' + len.toFixed(2) + ' ' + (C - len).toFixed(2) +
                        '" stroke-dashoffset="' + (-offset).toFixed(2) + '" transform="rotate(-90 ' + cx + ' ' + cy + ')"/>';
                    offset += len;
                });
            }
            return '<svg width="140" height="140" viewBox="0 0 140 140">' + partes +
                '<text x="' + cx + '" y="' + (cy + 2) + '" text-anchor="middle" fill="#172A44" font-size="26" font-weight="700" stroke="none">' +
                totalCentro + '</text>' +
                '<text x="' + cx + '" y="' + (cy + 20) + '" text-anchor="middle" fill="#5D7088" font-size="10" stroke="none">hallazgos</text>' +
                '</svg>';
        }

        function renderSeveridad(m) {
            const el = document.getElementById('severidadCuerpo');
            const s = (m && m.severidad) || {critical: 0, error: 0, warning: 0};
            const total = (s.critical || 0) + (s.error || 0) + (s.warning || 0);
            const segmentos = [
                {valor: s.critical || 0, color: '#C53030'},
                {valor: s.error || 0, color: '#C05621'},
                {valor: s.warning || 0, color: '#B7791F'}
            ];
            const leyenda =
                '<div class="item"><span class="punto sev-critical"></span>Crítico<span class="n">' + (s.critical || 0) + '</span></div>' +
                '<div class="item"><span class="punto sev-error"></span>Error<span class="n">' + (s.error || 0) + '</span></div>' +
                '<div class="item"><span class="punto sev-warning"></span>Advertencia<span class="n">' + (s.warning || 0) + '</span></div>';
            el.innerHTML = donaSvg(segmentos, total) + '<div class="severidad-leyenda">' + leyenda + '</div>' +
                (total === 0 ? '<div class="gauge-cobertura">Sin hallazgos de problema.</div>' : '');
        }

        function renderCategorias(m) {
            const el = document.getElementById('categoriasCuerpo');
            const cats = (m && m.categorias) || [];
            if (!cats.length) { el.innerHTML = '<p class="sin-datos">Sin datos.</p>'; return; }
            let html = '';
            cats.forEach(c => {
                const ok = c.ok || 0, sin = c.sin_datos || 0;
                const err = (c.error || 0) + (c.timeout || 0), ne = c.no_evaluado || 0;
                const hall = c.hallazgos || {};
                const total = ok + sin + err + ne || 1;
                const pct = v => (v / total * 100).toFixed(1) + '%';
                html += '<div class="categoria">';
                html += '<div class="nombre"><span>' + escHtml(c.paquete || 'Análisis') + '</span>' +
                    '<span>' + ok + ' OK · ' + sin + ' s/d · ' + err + ' error · ' + ne +
                    ' n/e · H C' + (hall.critical || 0) + ' E' + (hall.error || 0) +
                    ' A' + (hall.warning || 0) + '</span></div>';
                html += '<div class="barra">';
                if (ok) html += '<span class="barra-ok" style="width:' + pct(ok) + '" title="OK: ' + ok + '"></span>';
                if (sin) html += '<span class="barra-sindatos" style="width:' + pct(sin) + '" title="Sin datos: ' + sin + '"></span>';
                if (err) html += '<span class="barra-error" style="width:' + pct(err) + '" title="Error: ' + err + '"></span>';
                if (ne) html += '<span class="barra-noevaluado" style="width:' + pct(ne) + '" title="No evaluado: ' + ne + '"></span>';
                html += '</div></div>';
            });
            html += '<div class="acciones-hint">OK / Sin datos / Error / No evaluado por paquete · H = hallazgos (crítico/error/advertencia).</div>';
            el.innerHTML = html;
        }

        function nivelDe(tipo, pct) {
            if (tipo === 'memoria') {
                if (pct >= 90) return 'rojo';
                if (pct >= 80) return 'ambar';
                return 'ok';
            }
            if (pct >= 90) return 'rojo';
            if (pct >= 75) return 'ambar';
            return 'ok';
        }

        function renderMedidores(m) {
            const el = document.getElementById('medidoresCuerpo');
            const med = (m && m.medidores) || {};
            let html = '';
            if (med.memoria && med.memoria.usado_porcentaje != null) {
                const p = med.memoria.usado_porcentaje;
                const nv = med.memoria.nivel || nivelDe('memoria', p);
                html += '<div class="medidor"><div class="nombre"><span>Memoria en uso</span><span>' + p + '%</span></div>' +
                    '<div class="pista"><span class="nivel-' + nv + '" style="width:' + Math.min(100, p) + '%"></span></div></div>';
            }
            (med.discos || []).forEach(d => {
                if (d.usado_porcentaje == null) return;
                const nv = d.nivel || nivelDe('discos', d.usado_porcentaje);
                html += '<div class="medidor"><div class="nombre"><span>Disco ' + escHtml(d.unidad || '') +
                    '</span><span>' + d.usado_porcentaje + '%</span></div>' +
                    '<div class="pista"><span class="nivel-' + nv + '" style="width:' + Math.min(100, d.usado_porcentaje) + '%"></span></div></div>';
            });
            const leyenda = (m && m.leyenda_medidores) ? '<div class="acciones-hint">' + escHtml(m.leyenda_medidores) + '</div>' : '';
            el.innerHTML = (html || '<p class="sin-datos">Sin datos.</p>') + leyenda;
        }

        function alcanceDeEntrada(e) {
            if (!e) return 'Análisis';
            if (e.tipo === 'full-scan' || e.paquete === 'full-scan') return 'Revisión total';
            return e.paquete_label || e.paquete || 'Análisis';
        }

        function renderUltimoAnalisis(lista) {
            const el = document.getElementById('ultimoAnalisis');
            const nota = document.getElementById('ultimoNota');
            if (!el) return;
            if (!lista || !lista.length) {
                el.innerHTML = '<p class="sin-datos">Ejecute un diagnóstico para ver aquí su resumen, con el mismo formato de resultados que la vista de diagnósticos.</p>';
                if (nota) nota.textContent = 'Sin análisis registrados';
                return;
            }
            const e = lista[0];
            const c = e.conteos || {};
            const fecha = (e.fecha || '').replace('T', ' ').slice(0, 19);
            const problemas = c.findings || 0;
            const clase = problemas === 0 ? 'success' : ((c.error || 0) > 0 ? 'error' : 'warning');
            if (nota) nota.textContent = 'Registrado el ' + fecha;
            el.innerHTML = '<div class="diag-card ' + clase + '">' +
                '<div class="diag-header"><span class="diag-title">' +
                escHtml(e.paquete_label || e.paquete || 'Análisis') + '</span>' +
                '<span class="diag-badge ' + (clase === 'success' ? 'ok' : clase) + '">' +
                (problemas === 0 ? 'Sin problemas' : problemas + ' problema(s)') + '</span></div>' +
                '<div class="diag-stats"><span>Colectores OK: ' + (c.ok || 0) + '</span>' +
                '<span>Con error: ' + (c.error || 0) + '</span>' +
                '<span>Sin datos: ' + (c.empty || 0) + '</span>' +
                '<span>Puntaje: ' + (e.puntaje == null ? '—' : e.puntaje + '/100') + '</span></div>' +
                '<button class="btn-small btn-copy" onclick="irARegistro()">Ver en el historial</button></div>';
        }

        function renderActividad(lista) {
            const el = document.getElementById('actividadCuerpo');
            if (!el) return;
            if (!lista || !lista.length) {
                el.innerHTML = '<p class="sin-datos">Todavía no hay análisis registrados.</p>';
                return;
            }
            let html = '';
            lista.slice(0, 6).forEach(e => {
                const fecha = (e.fecha || '').replace('T', ' ').slice(0, 16);
                const col = (e.puntaje == null) ? '#5D7088' : (e.puntaje >= 85 ? '#157F45' : (e.puntaje >= 60 ? '#B7791F' : '#C53030'));
                html += '<div class="act-item">' +
                    '<span class="act-paq">' + escHtml(alcanceDeEntrada(e)) + '</span>' +
                    '<span class="act-puntaje" style="color:' + col + '">' + (e.puntaje == null ? '—' : e.puntaje) + '</span>' +
                    '<span class="act-fecha">' + escHtml(fecha) + '</span>' +
                    '</div>';
            });
            el.innerHTML = html;
        }

        function renderTendencia(lista) {
            const el = document.getElementById('tendenciaCuerpo');
            const nota = document.getElementById('tendenciaNota');
            if (!el) return;
            if (!lista || !lista.length) {
                el.innerHTML = '<p class="sin-datos">Aún no hay historial suficiente.</p>';
                if (nota) nota.textContent = '';
                return;
            }
            const ult = lista[0];
            const tipo = ult.tipo, paquete = ult.paquete;
            const puntos = lista
                .filter(e => e.tipo === tipo && e.paquete === paquete && e.puntaje != null)
                .slice(0, 10)
                .reverse();
            if (nota) nota.textContent = 'Tendencia: ' + alcanceDeEntrada(ult) + ' (últimos ' + puntos.length + ')';
            if (puntos.length < 2) {
                el.innerHTML = '<p class="sin-datos">Aún no hay historial suficiente.</p>';
                return;
            }
            const W = 600, H = 140, padX = 30, padY = 20;
            const n = puntos.length;
            const paso = (W - padX * 2) / (n - 1);
            const y = v => H - padY - (v / 100) * (H - padY * 2);
            let linea = '', area = '';
            puntos.forEach((p, i) => {
                const x = padX + i * paso;
                const yy = y(p.puntaje);
                linea += (i === 0 ? 'M ' : 'L ') + x.toFixed(1) + ' ' + yy.toFixed(1) + ' ';
                area += (i === 0 ? 'M ' : 'L ') + x.toFixed(1) + ' ' + yy.toFixed(1) + ' ';
            });
            const first = padX, last = padX + (n - 1) * paso;
            area = area.trim() + ' L ' + last.toFixed(1) + ' ' + (H - padY) + ' L ' + first.toFixed(1) + ' ' + (H - padY) + ' Z';
            let circulos = '', etiquetas = '';
            puntos.forEach((p, i) => {
                const x = padX + i * paso;
                const yy = y(p.puntaje);
                circulos += '<circle class="spark-punto" cx="' + x.toFixed(1) + '" cy="' + yy.toFixed(1) + '" r="3.5"/>';
                if (i === 0 || i === n - 1) {
                    etiquetas += '<text class="spark-txt" x="' + x.toFixed(1) + '" y="' + (yy - 8).toFixed(1) + '" text-anchor="middle">' + p.puntaje + '</text>';
                    etiquetas += '<text class="spark-txt" x="' + x.toFixed(1) + '" y="' + (H - 6) + '" text-anchor="middle">' +
                        escHtml((p.fecha || '').slice(5, 10)) + '</text>';
                }
            });
            el.innerHTML = '<svg class="spark" viewBox="0 0 ' + W + ' ' + H + '" preserveAspectRatio="none">' +
                '<line class="spark-eje" x1="' + padX + '" y1="' + y(100) + '" x2="' + (W - padX) + '" y2="' + y(100) + '"/>' +
                '<line class="spark-eje" x1="' + padX + '" y1="' + y(0) + '" x2="' + (W - padX) + '" y2="' + y(0) + '"/>' +
                '<path class="spark-area" d="' + area + '"/>' +
                '<path class="spark-linea" d="' + linea.trim() + '"/>' +
                circulos + etiquetas + '</svg>';
        }

        // ---------------------------------------------------------------
        // Base de conocimiento
        // ---------------------------------------------------------------
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
                if (e.por_que_importa) html += '<div class="kb-muted" style="color:#5D7088; margin-top:4px;"><b>Por qué importa:</b> ' + escHtml(e.por_que_importa) + '</div>';
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
                html += '<h4>' + escHtml(e.paquete_label || e.paquete || '-') +
                    (e.puntaje == null ? '' : ' <span class="badge-grupo">' + e.puntaje + '/100</span>') + '</h4>';
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
                        const color = f.severity === 'critical' ? '#C53030' :
                                     (f.severity === 'error' ? '#C05621' :
                                     (f.severity === 'warning' ? '#B7791F' : '#157F45'));
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
                const lbl = document.querySelector('#btnRegistro .mod-label');
                if (lbl) {
                    lbl.textContent = regEntradas.length ?
                        ('Registro de análisis (' + regEntradas.length + ')') :
                        'Registro de análisis';
                }
                renderTendencia(regEntradas);
                renderActividad(regEntradas);
                renderUltimoAnalisis(regEntradas);
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

        function pintarConteosDatos(c) {
            setTexto('datosRegistro', String((c && c.registro) || 0));
            setTexto('datosSnapshots', String((c && c.snapshots) || 0));
            setTexto('datosInformes', String((c && c.informes) || 0));
        }

        async function borrarDatosLocales() {
            try {
                const preview = await fetch('/api/datos', {
                    method: 'DELETE',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({confirmar: false})
                });
                const pd = await preview.json();
                if (!pd.conteos) throw new Error(pd.error || ('HTTP ' + preview.status));
                pintarConteosDatos(pd.conteos);
                const c = pd.conteos;
                if (!confirm('Se borrarán ' + c.registro + ' análisis, ' + c.snapshots +
                             ' snapshots y ' + c.informes + ' informes. La configuración y ' +
                             'la base de conocimiento no se modifican. ¿Continuar?')) return;

                const r = await fetch('/api/datos', {
                    method: 'DELETE',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({confirmar: true})
                });
                const d = await r.json();
                if (!r.ok) throw new Error(d.error || ('HTTP ' + r.status));
                pintarConteosDatos(d.eliminados);
                setTexto('datosEstado', 'Datos locales eliminados.');
                setStatus('ready', 'Datos locales eliminados');
                await loadRegistro();
            } catch (e) {
                setTexto('datosEstado', 'No se pudieron borrar los datos locales: ' + e.message);
                setStatus('error', 'Error al borrar datos locales');
            }
        }

        async function cerrarDiagUSB() {
            if (!confirm('¿Cerrar DiagUSB? La interfaz dejará de estar disponible hasta que lo abras de nuevo.')) return;
            const btn = document.getElementById('btnCerrarDiagUSB');
            const estado = document.getElementById('cierreEstado');
            if (btn) btn.disabled = true;
            try {
                const r = await fetch('/api/apagar', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: '{}'
                });
                const d = await r.json();
                if (!r.ok || !d.ok) throw new Error(d.error || ('HTTP ' + r.status));
                if (estado) estado.textContent = d.mensaje || 'DiagUSB se cerró.';
                setStatus('ready', 'DiagUSB cerrado');
            } catch (e) {
                if (estado) estado.textContent = 'No se pudo cerrar DiagUSB: ' + e.message;
                if (btn) btn.disabled = false;
                setStatus('error', 'Error al cerrar DiagUSB');
            }
        }

        // ---------------------------------------------------------------
        // Elevacion / permisos
        // ---------------------------------------------------------------
        async function loadIdentidad() {
            const b = document.getElementById('identidadBanner');
            if (!b) return;
            try {
                const r = await fetch('/api/identidad');
                const d = await r.json();
                const nombre = d.computer_name ? escHtml(d.computer_name) : '(sin nombre)';
                if (d.id_corto) {
                    const firme = (d.nivel === 'fuerte' && d.calidad === 'alta');
                    b.className = 'identidad-banner' + (firme ? '' : ' warn');
                    b.innerHTML = '<b>Equipo:</b> ' + nombre + ' &middot; <b>ID:</b> <span class="id-codigo">' + escHtml(d.id_corto) + '</span> &middot; identificaci\u00f3n ' + escHtml(d.nivel || '') + (d.aviso ? '<br>' + escHtml(d.aviso) : '');
                } else {
                    b.className = 'identidad-banner warn';
                    b.innerHTML = '<b>Equipo:</b> ' + nombre + ' &middot; <b>ID:</b> sin identificar<br>' + escHtml(d.aviso || '');
                }
            } catch (e) {
                b.className = 'identidad-banner warn';
                b.textContent = 'No se pudo consultar la identidad del equipo.';
            }
        }

        async function loadElevation() {
            try {
                const r = await fetch('/api/elevation');
                const d = await r.json();
                const b = document.getElementById('elevBanner');
                const rb = document.getElementById('respaldoBanner');
                const pe = document.getElementById('permisosEstado');
                const pd = document.getElementById('permisosDetalle');
                const cp = document.getElementById('configProceso');
                const ce = document.getElementById('configPermisos');
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
                    if (pe) { pe.className = 'permisos-estado ok'; pe.textContent = 'Administrador activo'; }
                    if (pd) pd.textContent = 'Inventario completo disponible.';
                    if (cp) cp.textContent = 'Administrador';
                    if (ce) { ce.className = 'config-estado ok'; ce.textContent = 'Se ejecuta con permisos de Administrador.'; }
                } else if (d.is_elevated === false) {
                    b.className = 'elev-banner warn';
                    b.innerHTML = '<b>Modo estándar:</b> datos limitados: installed_software (requiere administrador); ' +
                        'los eventos de seguridad no se evalúan. ' +
                        '<button type="button" class="elev-btn" id="elevBtn">Dar permisos de administrador</button>' +
                        '<div class="elev-msg" id="elevMsg"></div>';
                    b.style.display = 'block';
                    if (pe) { pe.className = 'permisos-estado warn'; pe.textContent = 'Modo estándar'; }
                    if (pd) pd.textContent = 'Algunos datos aparecen limitados.';
                    if (cp) cp.textContent = 'Usuario estándar';
                    if (ce) { ce.className = 'config-estado warn'; ce.textContent = 'Se ejecuta en modo estándar (datos limitados).'; }
                    const eb = document.getElementById('elevBtn');
                    if (eb) eb.addEventListener('click', solicitarElevacion);
                } else {
                    if (pe) { pe.className = 'permisos-estado'; pe.textContent = 'No se pudo determinar'; }
                    if (pd) pd.textContent = '—';
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

        // ---------------------------------------------------------------
        // Inicializacion
        // ---------------------------------------------------------------
        function inicializarAcerca() {
            document.querySelectorAll('[data-version]:not(body)').forEach(el => {
                el.textContent = DIAGUSB.version || '—';
            });
            setTexto('acercaHost', DIAGUSB.hostport || '—');
            setTexto('acercaDir', DIAGUSB.datadir || '—');
            setTexto('configDatos', DIAGUSB.datadir || '—');
            const ap = document.getElementById('acercaPuntaje');
            if (ap) {
                ap.textContent = 'El puntaje orientativo resta 15, 8 y 3 puntos por hallazgo ' +
                    'crítico, error y advertencia respectivamente, solo sobre los módulos ejecutados. ' +
                    'Un análisis de un paquete no refleja el estado general del equipo.';
            }
        }

        document.addEventListener('DOMContentLoaded', () => {
            latidoDiagUSB();
            setInterval(latidoDiagUSB, 4000);
            window.addEventListener('pagehide', ev => {
                if (!ev.persisted) despedidaDiagUSB();
            });
            document.querySelectorAll('#navPrincipal .nav-item').forEach(b =>
                b.addEventListener('click', () => mostrarVista(b.getAttribute('data-view'))));
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
            inicializarAcerca();
            loadIdentidad();
            cargarReferencia();
            cargarEntrega();
            cargarLiveUSB();
            conectarPruebaPerifericos();
            loadElevation();
            cargarCapacidades(false);
            loadRegistro();
        });
