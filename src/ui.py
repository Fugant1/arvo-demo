"""
Interface Web Single-Page Application (HTML5/JS/Tailwind) para operar visualmente:
Passo 1: POST /analyze (Upload do PDF -> Docling -> Triage -> Planner/MCP -> Critic -> Pausa HITL)
Passo 2: POST /hitl/{thread_id} (Deliberação Humana: Aprovar ou Editar Glosas -> Retomada LangGraph -> Persistência NoSQL DPO)
"""


def get_single_page_ui_html() -> str:
    return """<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>Arvo Audit AI — Auditoria de Contas Médicas TISS (LangGraph + Docling + MCP + DPO)</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <style>
    body { font-family: 'Inter', system-ui, -apple-system, sans-serif; background-color: #0f172a; color: #f8fafc; }
    .card { background-color: #1e293b; border: 1px solid #334155; border-radius: 0.75rem; }
    .badge { padding: 0.15rem 0.55rem; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; }
    pre { white-space: pre-wrap; word-wrap: break-word; }
  </style>
</head>
<body class="min-h-screen p-6">
  <div class="max-w-7xl mx-auto space-y-6">
    <!-- Cabeçalho -->
    <header class="card p-6 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
      <div>
        <div class="flex items-center gap-3">
          <span class="badge bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">LangGraph + Docling + FastMCP</span>
          <span class="badge bg-sky-500/20 text-sky-300 border border-sky-500/40">LiteLLM Router</span>
          <span class="badge bg-purple-500/20 text-purple-300 border border-purple-500/40">HITL + NoSQL DPO</span>
        </div>
        <h1 class="text-2xl font-bold mt-2 text-white">Agente de Auditoria de Contas Médicas com Autocorreção e HITL</h1>
        <p class="text-slate-400 text-sm mt-1">
          Fluxo Multiagente: <code class="text-sky-300">Docling Extractor → Triage Router (Flash-Lite) → Planner/Executor (MCP SQL+RAG) → Critic → HITL Interrupt</code>
        </p>
      </div>
      <div class="flex flex-col items-end gap-2">
        <div id="threadBadge" class="hidden px-3 py-1.5 rounded-lg bg-amber-500/20 border border-amber-400/40 text-amber-300 text-xs font-mono">
          Thread: <span id="activeThreadId">-</span>
        </div>
      </div>
    </header>

    <!-- PASSO 1: Ingestão e Execução até o Interrupt HITL -->
    <section class="card p-6 space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-semibold text-emerald-400">Passo 1 — Submissão da Guia TISS (POST /analyze)</h2>
        <span id="step1Status" class="badge bg-slate-700 text-slate-300">Aguardando envio</span>
      </div>
      <p class="text-sm text-slate-300">
        Selecione o PDF da Guia TISS (<code class="text-amber-300">guia_tiss_auditoria_arvo_teste.pdf</code>) ou execute diretamente com o documento padrão do repositório.
      </p>
      <div class="grid grid-cols-1 md:grid-cols-3 gap-4 items-end">
        <div>
          <label class="block text-xs text-slate-400 mb-1">Arquivo PDF da Guia Médica (opcional — usa PDF padrão se vazio)</label>
          <input id="pdfFileInput" type="file" accept=".pdf"
            class="w-full text-sm text-slate-300 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:text-sm file:font-semibold file:bg-slate-700 file:text-white hover:file:bg-slate-600 bg-slate-900 rounded-lg border border-slate-700 p-1.5" />
        </div>
        <div>
          <label class="block text-xs text-slate-400 mb-1">GEMINI_API_KEY (opcional caso não esteja no .env)</label>
          <input id="apiKeyInput" type="password" placeholder="AIzaSy... (deixe em branco para usar .env)"
            class="w-full text-sm bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-emerald-500" />
        </div>
        <div class="flex gap-2">
          <button id="btnAnalyze" onclick="runAnalyze()"
            class="w-full py-2.5 px-4 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm transition flex items-center justify-center gap-2 shadow-lg">
            <span>Executar Docling + LangGraph (/analyze)</span>
          </button>
        </div>
      </div>
    </section>

    <!-- Painel de Resultados Intermediários (Exibido após /analyze) -->
    <div id="analysisResultsContainer" class="hidden space-y-6">
      <!-- Cards Financeiros e Métricas -->
      <div class="grid grid-cols-1 md:grid-cols-4 gap-4">
        <div class="card p-4">
          <div class="text-xs text-slate-400">Valor Total Faturado (PDF)</div>
          <div id="valFaturado" class="text-2xl font-bold text-white mt-1">R$ 0,00</div>
          <div id="infoGuia" class="text-xs text-slate-400 mt-1">-</div>
        </div>
        <div class="card p-4 border-rose-500/40">
          <div class="text-xs text-rose-300">Total Glosado Sugerido (IA)</div>
          <div id="valGlosado" class="text-2xl font-bold text-rose-400 mt-1">R$ 0,00</div>
          <div id="qtdGlosas" class="text-xs text-rose-300/80 mt-1">0 inconsistências detectadas</div>
        </div>
        <div class="card p-4 border-emerald-500/40">
          <div class="text-xs text-emerald-300">Valor Líquido Aprovado Sugerido</div>
          <div id="valAprovado" class="text-2xl font-bold text-emerald-400 mt-1">R$ 0,00</div>
          <div class="text-xs text-emerald-300/80 mt-1">Validado pelo Nó Critic</div>
        </div>
        <div class="card p-4 border-sky-500/40">
          <div class="text-xs text-sky-300">Métricas Globais (Latência & Tokens)</div>
          <div id="valLatency" class="text-xl font-bold text-sky-400 mt-1">0 ms</div>
          <div id="valTokens" class="text-xs text-sky-300/80 mt-1">0 tokens consumidos</div>
        </div>
      </div>

      <!-- Telemetria por Nó (Docling + LiteLLM Router) e Parecer do Critic -->
      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="card p-5 space-y-3">
          <h3 class="text-sm font-semibold text-sky-400 uppercase tracking-wider">Telemetria de Nós (Docling & LiteLLM Model Routing)</h3>
          <div class="overflow-x-auto">
            <table class="w-full text-left text-xs">
              <thead class="text-slate-400 border-b border-slate-700">
                <tr>
                  <th class="py-2">Etapa / Nó</th>
                  <th class="py-2">Modelo Roteado</th>
                  <th class="py-2 text-right">Latência (ms)</th>
                  <th class="py-2 text-right">Prompt</th>
                  <th class="py-2 text-right">Compl.</th>
                  <th class="py-2 text-right">Total Tokens</th>
                </tr>
              </thead>
              <tbody id="metricsTableBody" class="divide-y divide-slate-800 font-mono"></tbody>
            </table>
          </div>
        </div>

        <div class="card p-5 space-y-3">
          <div class="flex items-center justify-between">
            <h3 class="text-sm font-semibold text-purple-400 uppercase tracking-wider">Validação Anti-Alucinação (Critic Node)</h3>
            <span id="criticBadge" class="badge bg-emerald-500/20 text-emerald-300">Aprovado</span>
          </div>
          <p id="criticFeedback" class="text-xs text-slate-300 bg-slate-900/90 p-3 rounded-lg border border-slate-800"></p>
          <div class="text-xs text-slate-400">
            <strong>Resumo da Triagem:</strong>
            <span id="triageSummaryText"></span>
          </div>
        </div>
      </div>

      <!-- PASSO 2: Revisão Humana (HITL) e Geração de Dataset DPO -->
      <section class="card p-6 space-y-5 border-2 border-amber-500/40">
        <div class="flex flex-col md:flex-row md:items-center justify-between gap-2">
          <div>
            <h2 class="text-lg font-semibold text-amber-400">
              Passo 2 — Revisão Human-in-the-Loop (POST /hitl/{thread_id})
            </h2>
            <p class="text-xs text-slate-300 mt-0.5">
              O grafo está pausado no <code class="text-amber-300">interrupt()</code>. Você pode aprovar integralmente as glosas sugeridas ou editar qualquer valor/justificativa na tabela abaixo para gerar o par contrastivo <code class="text-purple-300">(prompt_context, chosen, rejected)</code> para DPO.
            </p>
          </div>
          <span id="step2Status" class="badge bg-amber-500/20 text-amber-300">Pausado no HITL</span>
        </div>

        <!-- Tabela Editável de Glosas Sugeridas -->
        <div class="overflow-x-auto">
          <table class="w-full text-left text-xs">
            <thead class="text-slate-400 border-b border-slate-700 bg-slate-900/60">
              <tr>
                <th class="p-2">Item / TUSS</th>
                <th class="p-2">Procedimento / OPME / Diária</th>
                <th class="p-2">Cobrado (R$)</th>
                <th class="p-2">Glosado Editável (R$)</th>
                <th class="p-2">Cláusula Contratual (MCP)</th>
                <th class="p-2">Justificativa Técnica (Editável p/ DPO)</th>
              </tr>
            </thead>
            <tbody id="glosasTableBody" class="divide-y divide-slate-800"></tbody>
          </table>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label class="block text-xs text-slate-400 mb-1">Identificação do Auditor Médico</label>
            <input id="auditorIdInput" type="text" value="dr.marcelo.auditor@saudeplena.com.br"
              class="w-full text-xs bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white" />
          </div>
          <div>
            <label class="block text-xs text-slate-400 mb-1">Observações da Auditoria Humana (incluídas no Parecer Final e DPO)</label>
            <input id="auditorNotesInput" type="text" placeholder="Ex: Homologado conforme evidências SQL e relato cirúrgico."
              class="w-full text-xs bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-white" />
          </div>
        </div>

        <div class="flex flex-wrap gap-3 pt-2">
          <button onclick="submitHITL('APPROVE')"
            class="py-2.5 px-5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold text-sm transition shadow">
            ✓ Aprovar Sugestão do Agente (APPROVE)
          </button>
          <button onclick="submitHITL('EDIT')"
            class="py-2.5 px-5 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-semibold text-sm transition shadow">
            ✎ Salvar Edições e Retomar Grafo (EDIT → DPO Chosen vs Agent Rejected)
          </button>
          <button onclick="submitHITL('REJECT')"
            class="py-2.5 px-5 rounded-lg bg-rose-700 hover:bg-rose-600 text-white font-semibold text-sm transition shadow">
            ✕ Rejeitar Glosas (REJECT)
          </button>
        </div>
      </section>
    </div>

    <!-- Painel Final Pós-HITL (Parecer Consolidado + Par DPO Persistido no TinyDB) -->
    <section id="hitlFinalContainer" class="hidden card p-6 space-y-5 border-2 border-emerald-500/50">
      <div class="flex items-center justify-between">
        <h2 class="text-lg font-semibold text-emerald-400">Auditoria Finalizada & Par de Preferência DPO Persistido (NoSQL)</h2>
        <span id="dpoRecordBadge" class="badge bg-purple-500/20 text-purple-300 font-mono">DPO ID: -</span>
      </div>

      <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <div class="space-y-2">
          <h3 class="text-xs font-semibold text-slate-400 uppercase">Parecer Técnico Final Homologado</h3>
          <pre id="finalParecerText" class="text-xs bg-slate-900 p-4 rounded-lg border border-slate-800 text-slate-200 max-h-96 overflow-y-auto"></pre>
        </div>
        <div class="space-y-2">
          <h3 class="text-xs font-semibold text-purple-300 uppercase">Registro na Coleção <code class="text-amber-300">dpo_preference_dataset</code> (prompt_context, chosen, rejected)</h3>
          <pre id="dpoPreviewJson" class="text-xs bg-slate-900 p-4 rounded-lg border border-slate-800 text-emerald-300 font-mono max-h-96 overflow-y-auto"></pre>
        </div>
      </div>
    </section>
  </div>

  <script>
    let currentThreadId = null;
    let currentGlosas = [];

    function formatBRL(val) {
      return Number(val || 0).toLocaleString('pt-BR', { style: 'currency', currency: 'BRL' });
    }

    async function runAnalyze() {
      const btn = document.getElementById('btnAnalyze');
      const statusBadge = document.getElementById('step1Status');
      const fileInput = document.getElementById('pdfFileInput');
      const apiKeyInput = document.getElementById('apiKeyInput');

      btn.disabled = true;
      btn.innerHTML = '<span>Processando Docling + Grafo Multiagente...</span>';
      statusBadge.className = 'badge bg-amber-500/20 text-amber-300';
      statusBadge.textContent = 'Executando...';
      document.getElementById('hitlFinalContainer').classList.add('hidden');

      try {
        const formData = new FormData();
        if (fileInput.files && fileInput.files.length > 0) {
          formData.append('file', fileInput.files[0]);
        }
        if (apiKeyInput.value.trim()) {
          formData.append('gemini_api_key', apiKeyInput.value.trim());
        }

        const resp = await fetch('/analyze', { method: 'POST', body: formData });
        if (!resp.ok) {
          const errText = await resp.text();
          throw new Error(errText || 'Falha ao executar /analyze');
        }
        const data = await resp.json();
        currentThreadId = data.thread_id;
        currentGlosas = data.glosas_sugeridas || [];

        document.getElementById('threadBadge').classList.remove('hidden');
        document.getElementById('activeThreadId').textContent = currentThreadId;
        statusBadge.className = 'badge bg-emerald-500/20 text-emerald-300';
        statusBadge.textContent = 'Pausado em HITL (' + currentThreadId + ')';

        // Financeiro
        const fin = data.resumo_financeiro || {};
        document.getElementById('valFaturado').textContent = formatBRL(fin.valor_total_faturado);
        document.getElementById('valGlosado').textContent = formatBRL(fin.valor_total_glosado);
        document.getElementById('valAprovado').textContent = formatBRL(fin.valor_total_aprovado);
        document.getElementById('infoGuia').textContent =
          'Guia ' + (data.header?.numero_guia || '') + ' • CPF ' + (data.header?.cpf_beneficiario || '');
        document.getElementById('qtdGlosas').textContent =
          currentGlosas.length + ' inconsistências técnicas fundamentadas';

        // Métricas
        document.getElementById('valLatency').textContent = Number(data.total_latency_ms || 0).toFixed(1) + ' ms';
        document.getElementById('valTokens').textContent = (data.total_tokens || 0) + ' tokens totais';

        const metricsBody = document.getElementById('metricsTableBody');
        metricsBody.innerHTML = '';
        (data.metrics || []).forEach(m => {
          const tr = document.createElement('tr');
          tr.innerHTML = `
            <td class="py-1.5 text-slate-200">${m.step_name}</td>
            <td class="py-1.5 text-sky-300">${m.model}</td>
            <td class="py-1.5 text-right">${Number(m.latency_ms).toFixed(1)}</td>
            <td class="py-1.5 text-right">${m.prompt_tokens}</td>
            <td class="py-1.5 text-right">${m.completion_tokens}</td>
            <td class="py-1.5 text-right font-semibold text-emerald-300">${m.total_tokens}</td>
          `;
          metricsBody.appendChild(tr);
        });

        // Critic & Triage
        const critic = data.critic_review || {};
        document.getElementById('criticFeedback').textContent = critic.feedback_correcao || '';
        const ts = data.triage_summary || {};
        document.getElementById('triageSummaryText').textContent =
          `${ts.suspicious_count || 0} itens suspeitos auditados em profundidade e ${ts.auto_approved_count || 0} itens de baixo valor aprovados automaticamente.`;

        // Tabela de Glosas
        renderGlosasTable(currentGlosas);
        document.getElementById('analysisResultsContainer').classList.remove('hidden');
      } catch (err) {
        alert('Erro na análise: ' + err.message);
        statusBadge.className = 'badge bg-rose-500/20 text-rose-300';
        statusBadge.textContent = 'Erro';
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<span>Executar Docling + LangGraph (/analyze)</span>';
      }
    }

    function renderGlosasTable(glosas) {
      const tbody = document.getElementById('glosasTableBody');
      tbody.innerHTML = '';
      glosas.forEach((g, idx) => {
        const tr = document.createElement('tr');
        tr.className = 'hover:bg-slate-800/50';
        tr.innerHTML = `
          <td class="p-2 font-mono text-amber-300 whitespace-nowrap">
            #${g.item_id}<br/><span class="text-white font-bold">${g.codigo_tuss}</span>
          </td>
          <td class="p-2 text-slate-200 max-w-xs">
            <div class="font-semibold">${g.descricao}</div>
            <span class="inline-block mt-1 px-2 py-0.5 rounded bg-rose-500/20 text-rose-300 text-[10px]">${g.tipo_anomalia}</span>
          </td>
          <td class="p-2 font-mono text-slate-300 whitespace-nowrap">${formatBRL(g.valor_cobrado)}</td>
          <td class="p-2 whitespace-nowrap">
            <input type="number" step="0.01" id="glosaVal_${idx}" value="${g.valor_glosado}"
              class="w-28 bg-slate-900 border border-slate-700 rounded px-2 py-1 text-rose-300 font-mono text-xs" />
          </td>
          <td class="p-2 text-slate-300 max-w-xs">
            <input type="text" id="glosaClause_${idx}" value="${g.clausula_contratual}"
              class="w-full bg-slate-900 border border-slate-700 rounded px-2 py-1 text-sky-300 text-xs" />
          </td>
          <td class="p-2">
            <textarea id="glosaJust_${idx}" rows="2"
              class="w-full bg-slate-900 border border-slate-700 rounded p-1.5 text-slate-200 text-xs">${g.justificativa_tecnica}</textarea>
          </td>
        `;
        tbody.appendChild(tr);
      });
    }

    async function submitHITL(action) {
      if (!currentThreadId) {
        alert('Execute o Passo 1 (/analyze) primeiro.');
        return;
      }
      const step2Badge = document.getElementById('step2Status');
      step2Badge.textContent = 'Enviando decisão HITL...';

      const editedGlosas = currentGlosas.map((g, idx) => {
        const cobrado = Number(g.valor_cobrado || 0);
        const glosado = Number(document.getElementById(`glosaVal_${idx}`).value || 0);
        const aprovado = Math.max(0, Number((cobrado - glosado).toFixed(2)));
        return {
          ...g,
          valor_glosado: glosado,
          valor_aprovado: aprovado,
          clausula_contratual: document.getElementById(`glosaClause_${idx}`).value,
          justificativa_tecnica: document.getElementById(`glosaJust_${idx}`).value,
        };
      });

      const payload = {
        action: action,
        auditor_id: document.getElementById('auditorIdInput').value || 'auditor@saudeplena.com.br',
        auditor_notes: document.getElementById('auditorNotesInput').value || '',
        chosen_glosas: action === 'REJECT' ? [] : editedGlosas,
      };

      try {
        const resp = await fetch(`/hitl/${currentThreadId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        if (!resp.ok) {
          const errText = await resp.text();
          throw new Error(errText || 'Falha ao enviar /hitl');
        }
        const data = await resp.json();
        step2Badge.className = 'badge bg-emerald-500/20 text-emerald-300';
        step2Badge.textContent = 'Finalizado (' + data.action + ')';

        document.getElementById('dpoRecordBadge').textContent = 'DPO ID: ' + data.dpo_record_id;
        document.getElementById('finalParecerText').textContent = data.parecer_final;
        document.getElementById('dpoPreviewJson').textContent = JSON.stringify(data.dpo_pair_preview, null, 2);
        document.getElementById('hitlFinalContainer').classList.remove('hidden');
        document.getElementById('hitlFinalContainer').scrollIntoView({ behavior: 'smooth' });
      } catch (err) {
        alert('Erro no HITL: ' + err.message);
        step2Badge.className = 'badge bg-rose-500/20 text-rose-300';
        step2Badge.textContent = 'Erro';
      }
    }
  </script>
</body>
</html>"""


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("src.app:app", host="0.0.0.0", port=8000, reload=False)
