"""
Stabilize UI Animations script.
Eliminates stepper flickering, visual layout shifting, and high-frequency DOM mutations.
"""

def main():
    path = "test-interface.html"
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    # 1. Permanent non-jumping stepper
    old_stepper = '<div id="ai-pipeline-stepper" class="pipeline-stepper" style="display:none;">'
    new_stepper = '<div id="ai-pipeline-stepper" class="pipeline-stepper" style="margin-top:16px;">'
    if old_stepper in content:
        content = content.replace(old_stepper, new_stepper)

    # 2. Stable timer box
    old_timer = '<span id="ai-timer-status" style="font-size:0.8rem; color:var(--text-secondary); display:none;">'
    new_timer = '<span id="ai-timer-status" style="font-size:0.8rem; color:#475569; display:none; align-items:center; gap:8px;">'
    if old_timer in content:
        content = content.replace(old_timer, new_timer)

    # 3. Stepper functions: single-pass deterministic updates without continuous innerHTML DOM thrashing
    old_stepper_funcs = """        function resetStepper() {
            const stepper = document.getElementById('ai-pipeline-stepper');
            if (stepper) stepper.style.display = 'block';
            for (let i = 1; i <= 10; i++) {
                const el = document.getElementById(`step-${i}`);
                if (el) {
                    el.className = 'step-item';
                    const numEl = el.querySelector('.step-num');
                    if (numEl) numEl.textContent = i;
                }
            }
        }

        function updateStepperStage(stageNum, status = 'active') {
            const stepper = document.getElementById('ai-pipeline-stepper');
            if (stepper) stepper.style.display = 'block';
            for (let i = 1; i <= 10; i++) {
                const el = document.getElementById(`step-${i}`);
                if (!el) continue;
                if (i < stageNum) {
                    el.className = 'step-item done';
                    el.querySelector('.step-num').innerHTML = '<i class="fa-solid fa-check"></i>';
                } else if (i === stageNum) {
                    el.className = `step-item ${status}`;
                    el.querySelector('.step-num').textContent = i;
                } else {
                    el.className = 'step-item';
                    el.querySelector('.step-num').textContent = i;
                }
            }
        }

        function completeStepper() {
            for (let i = 1; i <= 10; i++) {
                const el = document.getElementById(`step-${i}`);
                if (el) {
                    el.className = 'step-item done';
                    el.querySelector('.step-num').innerHTML = '<i class="fa-solid fa-check"></i>';
                }
            }
        }"""

    new_stepper_funcs = """        function resetStepper() {
            for (let i = 1; i <= 10; i++) {
                const el = document.getElementById(`step-${i}`);
                if (el) el.className = 'step-item';
            }
        }

        function setStepperRunning() {
            for (let i = 1; i <= 7; i++) {
                const el = document.getElementById(`step-${i}`);
                if (el) el.className = 'step-item done';
            }
            const step8 = document.getElementById('step-8');
            if (step8) step8.className = 'step-item active';
            const step9 = document.getElementById('step-9');
            if (step9) step9.className = 'step-item';
            const step10 = document.getElementById('step-10');
            if (step10) step10.className = 'step-item';
        }

        function updateStepperStage(stageNum, status = 'active') {
            for (let i = 1; i <= 10; i++) {
                const el = document.getElementById(`step-${i}`);
                if (!el) continue;
                if (i < stageNum) {
                    el.className = 'step-item done';
                } else if (i === stageNum) {
                    el.className = `step-item ${status}`;
                } else {
                    el.className = 'step-item';
                }
            }
        }

        function completeStepper() {
            for (let i = 1; i <= 10; i++) {
                const el = document.getElementById(`step-${i}`);
                if (el) el.className = 'step-item done';
            }
        }"""

    if old_stepper_funcs in content:
        content = content.replace(old_stepper_funcs, new_stepper_funcs)
    else:
        print("Warning: old_stepper_funcs exact match not found!")

    # 4. Refine executeAITask to avoid timer thrashing, set calm placeholder, and smooth output
    old_exec_target = """            resetStepper();
            updateStepperStage(1, 'active');
            let timerInterval = null;
            let startTime = performance.now();

            btn.disabled = true;
            timerBox.style.display = 'inline-flex';

            const payload = {
                input: prompt,
                data_sensitivity: sensitivity,
                model: model,
                structured: isStructured
            };
            if (tool) {
                payload.tool = tool;
                payload.tool_parameters = tool === 'calculator' ? { expression: prompt.replace(/[^0-9+\-*/().]/g, '') || '2+2' } : {};
            }

            let res;
            try {
                timerInterval = setInterval(() => {
                    let elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
                    timerText.textContent = `Inference in progress with ${model} (${elapsed}s)...`;
                }, 100);

                setTimeout(() => updateStepperStage(2, 'active'), 120);
                setTimeout(() => updateStepperStage(3, 'active'), 240);
                setTimeout(() => updateStepperStage(4, 'active'), 360);
                setTimeout(() => updateStepperStage(5, 'active'), 500);
                setTimeout(() => updateStepperStage(7, 'active'), 700);
                setTimeout(() => updateStepperStage(8, 'active'), 900);

                res = await api('POST', '/api/v1/ai/execute', payload);
            } finally {
                if (timerInterval) clearInterval(timerInterval);
                btn.disabled = false;
                timerBox.style.display = 'none';
            }"""

    new_exec_target = """            resetStepper();
            setStepperRunning();
            let timerInterval = null;
            let startTime = performance.now();

            btn.disabled = true;
            btn.innerHTML = `<i class="fa-solid fa-spinner fa-spin"></i> Executing...`;
            timerBox.style.display = 'inline-flex';
            timerText.textContent = `Inference running with ${model} (0.0s)...`;

            const box = document.getElementById('ai-result-box');
            const chips = document.getElementById('ai-summary-chips');
            const ansCard = document.getElementById('ai-answer-card');
            const ansText = document.getElementById('ai-answer-text');
            const ansMeta = document.getElementById('ai-answer-meta');
            const sourcesCard = document.getElementById('ai-sources-card');
            const citationsCard = document.getElementById('ai-citations-card');
            const withheldBanner = document.getElementById('ai-withheld-alert');

            // Set clean, calm loading placeholder inside the result box without flickering
            box.style.display = 'block';
            chips.innerHTML = '<span class="badge badge-info"><i class="fa-solid fa-spinner fa-spin"></i> Executing Pipeline</span>';
            sourcesCard.style.display = 'none';
            if (citationsCard) citationsCard.style.display = 'none';
            if (withheldBanner) withheldBanner.style.display = 'none';
            ansCard.style.display = 'block';
            ansCard.style.borderLeft = '5px solid #0284c7';
            ansMeta.textContent = `Engine: ${model} | Status: executing`;
            ansText.innerHTML = `
                <div style="padding:28px 16px; text-align:center; color:#64748b;">
                    <i class="fa-solid fa-circle-notch fa-spin" style="font-size:2rem; color:#0284c7; margin-bottom:12px;"></i>
                    <div style="font-weight:600; color:#0f172a; font-size:0.95rem; margin-bottom:4px;">Executing Zero-Trust Inference Pipeline</div>
                    <div style="font-size:0.8rem; color:#64748b;">Enforcing RBAC clearances, retrieving organizational context, and querying local Ollama runtime...</div>
                </div>
            `;

            const payload = {
                input: prompt,
                data_sensitivity: sensitivity,
                model: model,
                structured: isStructured
            };
            if (tool) {
                payload.tool = tool;
                payload.tool_parameters = tool === 'calculator' ? { expression: prompt.replace(/[^0-9+\-*/().]/g, '') || '2+2' } : {};
            }

            let res;
            try {
                timerInterval = setInterval(() => {
                    let elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
                    timerText.textContent = `Inference running with ${model} (${elapsed}s)...`;
                }, 500);

                res = await api('POST', '/api/v1/ai/execute', payload);
            } finally {
                if (timerInterval) clearInterval(timerInterval);
                btn.disabled = false;
                btn.innerHTML = `<i class="fa-solid fa-play"></i> Execute Pipeline`;
                timerBox.style.display = 'none';
            }"""

    if old_exec_target in content:
        content = content.replace(old_exec_target, new_exec_target)
    else:
        print("Warning: old_exec_target exact match not found!")

    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    print("UI animations stabilized successfully!")

if __name__ == "__main__":
    main()
