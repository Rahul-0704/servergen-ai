import re

with open('test-interface.html', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update renderMarkdown to handle structured output
old_render_md = """        function renderMarkdown(text) {
            if (!text) return '';
            let html = text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');

            // Headers
            html = html.replace(/^### (.*$)/gim, '<h4>$1</h4>');
            html = html.replace(/^## (.*$)/gim, '<h3>$1</h3>');
            html = html.replace(/^# (.*$)/gim, '<h2>$1</h2>');

            // Code blocks
            html = html.replace(/```([a-z]*)\\n([\\s\\S]*?)```/gim, '<pre><code>$2</code></pre>');
            // Inline Code
            html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

            // Bold & Italic
            html = html.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
            html = html.replace(/\\*(.*?)\\*/g, '<em>$1</em>');

            // Citations [Source: ...]
            html = html.replace(/\\[Source:\\s*([^\\]]+)\\]/gi, '<span class="badge badge-success"><i class="fa-solid fa-book"></i> Source: $1</span>');

            // Bullet points
            html = html.replace(/^\\s*[-*]\\s+(.*$)/gim, '<li>$1</li>');
            html = html.replace(/^\\s*(\\d+)\\.\\s+(.*$)/gim, '<li><strong>$1.</strong> $2</li>');

            // Line breaks
            html = html.replace(/\\n\\n/g, '<div style="height:10px;"></div>');
            html = html.replace(/\\n(?![<\\/?(h\\d|li|div|pre|code)])/g, '<br>');

            return html;
        }"""

new_render_md = """        function renderMarkdown(text) {
            if (!text) return '';

            // Check if text is structured JSON output (from StructuredTaskOutput)
            const trimmed = text.trim();
            if (trimmed.startsWith('{') && trimmed.endsWith('}')) {
                try {
                    const parsed = JSON.parse(trimmed);
                    if (parsed.summary || parsed.details || parsed.action_items) {
                        let out = '<div class="structured-output-card">';
                        if (parsed.summary) {
                            out += `<div class="structured-summary-box">
                                <div class="structured-heading"><i class="fa-solid fa-file-lines"></i> Executive Summary</div>
                                <div class="structured-summary-text">${renderMarkdown(parsed.summary)}</div>
                            </div>`;
                        }
                        if (parsed.details && Array.isArray(parsed.details) && parsed.details.length > 0) {
                            out += `<div class="structured-section">
                                <div class="structured-heading"><i class="fa-solid fa-list-check"></i> Key Details & Analysis</div>
                                <ul class="structured-list">
                                    ${parsed.details.map(d => `<li><i class="fa-solid fa-circle-check text-success" style="margin-top:3px;"></i> <span>${renderMarkdown(d)}</span></li>`).join('')}
                                </ul>
                            </div>`;
                        }
                        if (parsed.action_items && Array.isArray(parsed.action_items) && parsed.action_items.length > 0) {
                            out += `<div class="structured-section">
                                <div class="structured-heading"><i class="fa-solid fa-arrow-right-to-bracket text-primary"></i> Recommended Operational Actions</div>
                                <ul class="structured-list actions">
                                    ${parsed.action_items.map((a, i) => `<li><span class="step-badge">${i+1}</span> <span>${renderMarkdown(a)}</span></li>`).join('')}
                                </ul>
                            </div>`;
                        }
                        out += '</div>';
                        return out;
                    }
                } catch (e) {
                    // Fall back to standard markdown formatting
                }
            }

            let html = text
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;');

            // Headers
            html = html.replace(/^### (.*$)/gim, '<h4>$1</h4>');
            html = html.replace(/^## (.*$)/gim, '<h3>$1</h3>');
            html = html.replace(/^# (.*$)/gim, '<h2>$1</h2>');

            // Code blocks
            html = html.replace(/```([a-z]*)\\n([\\s\\S]*?)```/gim, '<pre><code>$2</code></pre>');
            // Inline Code
            html = html.replace(/`([^`]+)`/g, '<code>$1</code>');

            // Bold & Italic
            html = html.replace(/\\*\\*(.*?)\\*\\*/g, '<strong>$1</strong>');
            html = html.replace(/\\*(.*?)\\*/g, '<em>$1</em>');

            // Citations [Source: ...]
            html = html.replace(/\\[Source:\\s*([^\\]]+)\\]/gi, '<span class="badge badge-success"><i class="fa-solid fa-book"></i> Source: $1</span>');

            // Bullet points
            html = html.replace(/^\\s*[-*]\\s+(.*$)/gim, '<li>$1</li>');
            html = html.replace(/^\\s*(\\d+)\\.\\s+(.*$)/gim, '<li><strong>$1.</strong> $2</li>');

            // Line breaks
            html = html.replace(/\\n\\n/g, '<div style="height:10px;"></div>');
            html = html.replace(/\\n(?![<\\/?(h\\d|li|div|pre|code)])/g, '<br>');

            return html;
        }"""

if old_render_md in text:
    text = text.replace(old_render_md, new_render_md)
    print("1. Updated renderMarkdown")
else:
    print("WARNING: old_render_md not matched")

# 2. Update executeAITask citations item styling & dual-custody approval display
old_cit_code = """                    d.citations.forEach(c => {
                        const item = document.createElement('div');
                        item.style.cssText = 'padding:6px 10px; background:#1e293b; border-radius:4px; font-size:0.8rem; display:flex; justify-content:space-between; align-items:center;';
                        const docTitle = c.document_title || c.title || 'Knowledge Base Document';
                        const score = c.relevance_score !== undefined ? Math.round(c.relevance_score * 100) : (c.score !== undefined ? Math.round(c.score * 100) : null);
                        const scoreBadge = score !== null ? `<span class="badge badge-success">${score}% match</span>` : '';
                        const chunkIdx = c.chunk_index !== undefined ? ` <span style="color:#64748b;">(chunk #${c.chunk_index})</span>` : '';
                        item.innerHTML = `<div><i class="fa-solid fa-file-lines" style="color:#38bdf8; margin-right:6px;"></i><strong>${docTitle}</strong>${chunkIdx}</div>${scoreBadge}`;
                        citationsList.appendChild(item);
                    });"""

new_cit_code = """                    d.citations.forEach(c => {
                        const item = document.createElement('div');
                        item.style.cssText = 'padding:8px 12px; background:#ffffff; border:1px solid #e2e8f0; border-radius:6px; font-size:0.8rem; display:flex; justify-content:space-between; align-items:center; margin-bottom:4px; box-shadow:0 1px 2px rgba(0,0,0,0.03);';
                        const docTitle = c.document_title || c.title || 'Knowledge Base Document';
                        const score = c.relevance_score !== undefined ? Math.round(c.relevance_score * 100) : (c.score !== undefined ? Math.round(c.score * 100) : null);
                        const scoreBadge = score !== null ? `<span class="badge badge-success">${score}% match</span>` : '';
                        const chunkIdx = c.chunk_index !== undefined ? ` <span style="color:#64748b;">(chunk #${c.chunk_index})</span>` : '';
                        item.innerHTML = `<div><i class="fa-solid fa-file-lines" style="color:#0284c7; margin-right:6px;"></i><strong style="color:#0f172a;">${docTitle}</strong>${chunkIdx}</div>${scoreBadge}`;
                        citationsList.appendChild(item);
                    });"""

if old_cit_code in text:
    text = text.replace(old_cit_code, new_cit_code)
    print("2. Updated citationsList rendering in executeAITask")
else:
    print("WARNING: old_cit_code not matched")

# 3. Update ansCard display in executeAITask
old_ans_card_code = """            if (d.content) {
                ansCard.style.display = 'block';
                ansText.innerHTML = renderMarkdown(d.content);
            } else if (d.tool_output) {
                ansCard.style.display = 'block';
                ansText.innerHTML = `<strong>Tool Execution Output:</strong><pre><code>${JSON.stringify(d.tool_output, null, 2)}</code></pre>`;
            } else if (d.error) {
                ansCard.style.display = 'block';
                ansText.innerHTML = `<div class="alert-banner danger"><i class="fa-solid fa-circle-exclamation"></i> <strong>Execution Notice:</strong> ${d.error}</div>`;
            } else {
                ansCard.style.display = 'none';
            }"""

new_ans_card_code = """            if (d.policy_decision === 'require_approval') {
                ansCard.style.display = 'block';
                ansCard.style.borderLeft = '5px solid #d97706';
                ansText.innerHTML = `
                    <div style="background:#fffbeb; border:1px solid #fde68a; border-radius:8px; padding:16px; margin-bottom:8px;">
                        <div style="display:flex; align-items:center; gap:8px; font-weight:700; color:#b45309; font-size:0.95rem; margin-bottom:6px;">
                            <i class="fa-solid fa-shield-halved" style="font-size:1.2rem;"></i> Dual-Custody Approval Required (Policy Engine Guardrail)
                        </div>
                        <div style="color:#78350f; font-size:0.85rem; line-height:1.5;">
                            This high-risk or sensitive operation has been intercepted by the Zero-Trust Policy Engine. Execution requires explicit sign-off from an authorized department manager.
                        </div>
                        <div style="margin-top:12px; display:flex; gap:10px; align-items:center;">
                            <span class="badge badge-warning" style="font-size:0.8rem;"><i class="fa-solid fa-ticket"></i> Ticket UUID: ${d.approval_id || 'PENDING'}</span>
                            <button class="btn btn-secondary btn-sm" onclick="switchNav('approvals', document.querySelectorAll('.nav-item')[5])"><i class="fa-solid fa-arrow-right"></i> Open Approvals Queue</button>
                        </div>
                    </div>`;
            } else if (d.content) {
                ansCard.style.display = 'block';
                ansCard.style.borderLeft = '5px solid #0284c7';
                ansText.innerHTML = renderMarkdown(d.content);
            } else if (d.tool_output) {
                ansCard.style.display = 'block';
                ansCard.style.borderLeft = '5px solid #059669';
                ansText.innerHTML = `<strong>Tool Execution Output:</strong><pre><code>${JSON.stringify(d.tool_output, null, 2)}</code></pre>`;
            } else if (d.error) {
                ansCard.style.display = 'block';
                ansCard.style.borderLeft = '5px solid #dc2626';
                ansText.innerHTML = `<div class="alert-banner danger"><i class="fa-solid fa-circle-exclamation"></i> <strong>Execution Notice:</strong> ${d.error}</div>`;
            } else {
                ansCard.style.display = 'none';
            }"""

if old_ans_card_code in text:
    text = text.replace(old_ans_card_code, new_ans_card_code)
    print("3. Updated ansCard handling in executeAITask")
else:
    print("WARNING: old_ans_card_code not matched")

# 4. Update previewDoc chunk card styles
old_prev_chunk = """                const card = document.createElement('div');
                card.style.background = '#0f172a';
                card.style.border = '1px solid #1e293b';
                card.style.borderRadius = '6px';
                card.style.padding = '12px';
                card.style.marginBottom = '10px';

                let loc = [];
                if (c.page_number) loc.push(`Page ${c.page_number}`);
                if (c.section_heading) loc.push(`Section: ${c.section_heading}`);
                const locStr = loc.length > 0 ? ` (${loc.join(', ')})` : '';

                card.innerHTML = `
                    <div style="display:flex; justify-content:space-between; margin-bottom:6px; font-size:0.75rem; color:#38bdf8; font-weight:600;">
                        <span>Chunk #${c.chunk_index + 1}${locStr}</span>
                        <span style="color:#94a3b8;">${c.token_count || 0} tokens</span>
                    </div>
                    <div style="font-size:0.82rem; color:#cbd5e1; white-space:pre-wrap; line-height:1.5;">${c.content}</div>
                `;"""

new_prev_chunk = """                const card = document.createElement('div');
                card.style.background = '#ffffff';
                card.style.border = '1px solid #e2e8f0';
                card.style.borderRadius = '6px';
                card.style.padding = '12px';
                card.style.marginBottom = '10px';
                card.style.boxShadow = '0 1px 2px rgba(0,0,0,0.03)';

                let loc = [];
                if (c.page_number) loc.push(`Page ${c.page_number}`);
                if (c.section_heading) loc.push(`Section: ${c.section_heading}`);
                const locStr = loc.length > 0 ? ` (${loc.join(', ')})` : '';

                card.innerHTML = `
                    <div style="display:flex; justify-content:space-between; margin-bottom:6px; font-size:0.75rem; color:#0284c7; font-weight:600;">
                        <span>Chunk #${c.chunk_index + 1}${locStr}</span>
                        <span style="color:#64748b;">${c.token_count || 0} tokens</span>
                    </div>
                    <div style="font-size:0.84rem; color:#1e293b; white-space:pre-wrap; line-height:1.5;">${c.content}</div>
                `;"""

if old_prev_chunk in text:
    text = text.replace(old_prev_chunk, new_prev_chunk)
    print("4. Updated previewDoc chunk card styling")
else:
    print("WARNING: old_prev_chunk not matched")

# 5. Update RAG Lab timeline and answer text
text = text.replace(
    "item.style.background = step.status === 'warning' ? 'rgba(245, 158, 11, 0.15)' : 'rgba(30, 41, 59, 0.5)';",
    "item.style.background = step.status === 'warning' ? '#fef3c7' : '#f1f5f9'; item.style.border = step.status === 'warning' ? '1px solid #fde68a' : '1px solid #e2e8f0'; item.style.color = '#0f172a';"
)
text = text.replace(
    "document.getElementById('rag-lab-answer-text').textContent = d.answer;",
    "document.getElementById('rag-lab-answer-text').innerHTML = renderMarkdown(d.answer);"
)

# 6. Update RAG Lab citations
old_lab_cit = """                    const el = document.createElement('div');
                    el.style.background = '#0f172a';
                    el.style.border = '1px solid #1e293b';
                    el.style.padding = '8px 12px';
                    el.style.borderRadius = '6px';
                    el.style.fontSize = '0.8rem';"""

new_lab_cit = """                    const el = document.createElement('div');
                    el.style.background = '#ffffff';
                    el.style.border = '1px solid #e2e8f0';
                    el.style.padding = '8px 12px';
                    el.style.borderRadius = '6px';
                    el.style.fontSize = '0.8rem';
                    el.style.boxShadow = '0 1px 2px rgba(0,0,0,0.03)';"""

text = text.replace(old_lab_cit, new_lab_cit)

# 7. Update RAG Lab retrieval-only chunks
old_lab_chunk = """                const el = document.createElement('div');
                el.style.background = '#111928';
                el.style.border = '1px solid #1e293b';
                el.style.padding = '12px';
                el.style.borderRadius = '6px';

                el.innerHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                        <span style="font-weight:600; color:#0f172a; font-size:0.85rem;">#${idx+1} ${c.document_title}</span>
                        <div style="display:flex; gap:6px;">
                            <span class="badge badge-info">${c.classification.toUpperCase()}</span>
                            <span class="badge badge-success">Score: ${c.relevance_score} (Sem: ${c.semantic_score}, Kw: ${c.keyword_score})</span>
                        </div>
                    </div>
                    <div style="font-size:0.8rem; color:#cbd5e1; white-space:pre-wrap; line-height:1.5;">${c.content}</div>
                `;"""

new_lab_chunk = """                const el = document.createElement('div');
                el.style.background = '#ffffff';
                el.style.border = '1px solid #e2e8f0';
                el.style.padding = '12px';
                el.style.borderRadius = '6px';
                el.style.boxShadow = '0 1px 2px rgba(0,0,0,0.03)';

                el.innerHTML = `
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:6px;">
                        <span style="font-weight:600; color:#0f172a; font-size:0.85rem;">#${idx+1} ${c.document_title}</span>
                        <div style="display:flex; gap:6px;">
                            <span class="badge badge-info">${c.classification.toUpperCase()}</span>
                            <span class="badge badge-success">Score: ${c.relevance_score} (Sem: ${c.semantic_score}, Kw: ${c.keyword_score})</span>
                        </div>
                    </div>
                    <div style="font-size:0.82rem; color:#1e293b; white-space:pre-wrap; line-height:1.5;">${c.content}</div>
                `;"""

text = text.replace(old_lab_chunk, new_lab_chunk)

# 8. Update showToast
old_toast = """            toast.style.cssText = `background:#1e293b; border-left:4px solid ${type === 'danger' ? '#ef4444' : (type === 'success' ? '#10b981' : '#38bdf8')}; color:#0f172a; padding:10px 16px; border-radius:6px; font-size:0.82rem; box-shadow:0 10px 25px rgba(0,0,0,0.5); pointer-events:auto; display:flex; align-items:center; gap:8px;`;"""
new_toast = """            toast.style.cssText = `background:#ffffff; border:1px solid #e2e8f0; border-left:4px solid ${type === 'danger' ? '#ef4444' : (type === 'success' ? '#10b981' : '#0284c7')}; color:#0f172a; padding:10px 16px; border-radius:6px; font-size:0.82rem; box-shadow:0 10px 25px rgba(0,0,0,0.1); pointer-events:auto; display:flex; align-items:center; gap:8px;`;"""
text = text.replace(old_toast, new_toast)

# 9. Clean all remaining dark borders across inline styles
text = text.replace('border:1px solid #1f2b3e;', 'border:1px solid #e2e8f0;')
text = text.replace('border:1px solid #1f293d;', 'border:1px solid #e2e8f0;')
text = text.replace('border:1px solid #334155;', 'border:1px solid #e2e8f0;')
text = text.replace('border: 1px solid #334155;', 'border: 1px solid #e2e8f0;')
text = text.replace('border:1px solid #1e293b;', 'border:1px solid #e2e8f0;')
text = text.replace('border: 1px solid #1e293b;', 'border: 1px solid #e2e8f0;')
text = text.replace('border-bottom:1px solid #1e293b;', 'border-bottom:1px solid #e2e8f0;')
text = text.replace('background:#334155; height:6px;', 'background:#e2e8f0; height:6px;')

# 10. Default slider min_relevance to 0.25
text = text.replace('min_relevance: <strong id="lbl-min-rel" style="color:#0f172a;">0.20</strong>', 'min_relevance: <strong id="lbl-min-rel" style="color:#0f172a;">0.25</strong>')
text = text.replace('id="rag-lab-minrel" min="0.05" max="0.80" step="0.05" value="0.20"', 'id="rag-lab-minrel" min="0.05" max="0.80" step="0.05" value="0.25"')
text = text.replace('parseFloat(document.getElementById(\'rag-lab-minrel\').value) || 0.20;', 'parseFloat(document.getElementById(\'rag-lab-minrel\').value) || 0.25;')

with open('test-interface.html', 'w', encoding='utf-8') as f:
    f.write(text)

print("test-interface.html polished successfully!")
