import re

with open('test-interface.html', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Add resetStepper function
old_stepper_def = """        function updateStepperStage(stageNum, status = 'active') {
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

new_stepper_def = """        function resetStepper() {
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

if old_stepper_def in text:
    text = text.replace(old_stepper_def, new_stepper_def)
    print("1. Added resetStepper definition")
else:
    print("WARNING: old_stepper_def not matched")

# 2. Fix api() 401 handling to use refresh_token instead of admin auto-escalation
old_api_401 = """                // Auto-recover if session expired mid-flight
                if (res.status === 401 && requireAuth && !url.includes('/auth/login')) {
                    console.warn('Session expired or unauthorized (401). Auto-reauthenticating as admin...');
                    sessionStorage.removeItem('servergen_token');
                    sessionStorage.removeItem('servergen_refresh');
                    await quickSwitchRole('admin', false);
                    if (state.token) {
                        headers['Authorization'] = 'Bearer ' + state.token;
                        const retryRes = await fetch(url, opts);
                        if (retryRes.status === 204) return { ok: true, status: 204, data: { success: true } };
                        const retryData = await retryRes.json().catch(() => ({}));
                        return { ok: retryRes.ok, status: retryRes.status, data: retryData };
                    }
                }"""

new_api_401 = """                // Auto-recover session using refresh token without privilege escalation
                if (res.status === 401 && requireAuth && !url.includes('/auth/login') && !url.includes('/auth/refresh')) {
                    if (state.refresh) {
                        try {
                            const refreshRes = await fetch('/api/v1/auth/refresh', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({ refresh_token: state.refresh })
                            });
                            if (refreshRes.ok) {
                                const refData = await refreshRes.json();
                                state.token = refData.access_token;
                                state.refresh = refData.refresh_token;
                                sessionStorage.setItem('servergen_token', state.token);
                                sessionStorage.setItem('servergen_refresh', state.refresh);
                                headers['Authorization'] = 'Bearer ' + state.token;
                                const retryRes = await fetch(url, opts);
                                if (retryRes.status === 204) return { ok: true, status: 204, data: { success: true } };
                                const retryData = await retryRes.json().catch(() => ({}));
                                return { ok: retryRes.ok, status: retryRes.status, data: retryData };
                            }
                        } catch (e) {
                            console.warn('Token refresh failed:', e);
                        }
                    }
                    showToast('Session expired. Please sign in again.', 'warning');
                    updateSessionBadge(false);
                }"""

if old_api_401 in text:
    text = text.replace(old_api_401, new_api_401)
    print("2. Fixed api() 401 token refresh")
else:
    print("WARNING: old_api_401 not matched")

# 3. Add try ... finally to executeAITask
old_execute = """            btn.disabled = true;
            timerBox.style.display = 'inline-flex';

            updateStepperStage(1, 'active');
            setTimeout(() => updateStepperStage(2, 'active'), 120);
            setTimeout(() => updateStepperStage(3, 'active'), 240);
            setTimeout(() => updateStepperStage(4, 'active'), 360);
            setTimeout(() => updateStepperStage(5, 'active'), 500);
            setTimeout(() => updateStepperStage(7, 'active'), 700);
            setTimeout(() => updateStepperStage(8, 'active'), 900);

            let startTime = performance.now();
            let timerInterval = setInterval(() => {
                let elapsed = ((performance.now() - startTime) / 1000).toFixed(1);
                timerText.textContent = `Inference in progress with ${model} (${elapsed}s)...`;
            }, 100);

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

            const res = await api('POST', '/api/v1/ai/execute', payload);

            clearInterval(timerInterval);
            completeStepper();
            let totalElapsed = ((performance.now() - startTime) / 1000).toFixed(2);
            btn.disabled = false;
            timerBox.style.display = 'none';"""

new_execute = """            resetStepper();
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
            }

            completeStepper();
            let totalElapsed = ((performance.now() - startTime) / 1000).toFixed(2);"""

if old_execute in text:
    text = text.replace(old_execute, new_execute)
    print("3. Wrapped executeAITask with try...finally and resetStepper")
else:
    print("WARNING: old_execute not matched")

with open('test-interface.html', 'w', encoding='utf-8') as f:
    f.write(text)

print("test-interface.html resilience updates complete!")
