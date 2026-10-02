/**
 * Gate Camera — capture, verify, and display results.
 *
 * Handles:
 *   - getUserMedia camera access (front/rear toggle)
 *   - Photo capture to canvas → blob
 *   - fetch() POST to /gate/verify/
 *   - Dynamic result rendering (MATCHED / NO_MATCH / REVIEW / DUPLICATE / BLOCKED)
 *   - Confirm Entry button
 *   - Auto-reset for next scan after 6 seconds
 *   - Upload fallback when camera is unavailable
 */

(function () {
    'use strict';

    // ── DOM refs ──
    const video           = document.getElementById('cameraFeed');
    const canvas          = document.getElementById('cameraCanvas');
    const captureBtn      = document.getElementById('captureBtn');
    const switchCameraBtn = document.getElementById('switchCameraBtn');
    const uploadInput     = document.getElementById('uploadInput');
    const processingOverlay = document.getElementById('processingOverlay');
    const cameraView      = document.getElementById('cameraView');
    const resultView      = document.getElementById('resultView');
    const gateKey         = document.getElementById('gateKey')?.value || '';

    let currentStream = null;
    let facingMode = 'environment';  // Start with rear camera
    let autoResetTimer = null;

    // ── Camera Setup ──
    async function startCamera() {
        try {
            if (currentStream) {
                currentStream.getTracks().forEach(t => t.stop());
            }
            const constraints = {
                video: {
                    facingMode: facingMode,
                    width: { ideal: 1280 },
                    height: { ideal: 960 },
                },
                audio: false,
            };
            currentStream = await navigator.mediaDevices.getUserMedia(constraints);
            video.srcObject = currentStream;
        } catch (err) {
            console.warn('Camera access failed:', err);
            // Show upload fallback prominently
            document.querySelector('.upload-fallback').style.bottom = '40%';
        }
    }

    // ── Switch Camera ──
    if (switchCameraBtn) {
        switchCameraBtn.addEventListener('click', function () {
            facingMode = facingMode === 'environment' ? 'user' : 'environment';
            startCamera();
        });
    }

    // ── Capture Photo ──
    function capturePhoto() {
        return new Promise((resolve) => {
            canvas.width = video.videoWidth || 640;
            canvas.height = video.videoHeight || 480;
            const ctx = canvas.getContext('2d');
            ctx.drawImage(video, 0, 0);
            canvas.toBlob(resolve, 'image/jpeg', 0.92);
        });
    }

    // ── Upload Fallback ──
    if (uploadInput) {
        uploadInput.addEventListener('change', async function (e) {
            const file = e.target.files[0];
            if (!file) return;
            await verifyPhoto(file);
        });
    }

    // ── Capture Button ──
    if (captureBtn) {
        captureBtn.addEventListener('click', async function () {
            const blob = await capturePhoto();
            if (blob) {
                await verifyPhoto(blob);
            }
        });
    }

    // ── Send to Server ──
    async function verifyPhoto(blob) {
        processingOverlay.style.display = 'flex';

        const formData = new FormData();
        formData.append('scan_photo', blob, 'scan.jpg');
        formData.append('key', gateKey);

        try {
            const response = await fetch('verify/', {
                method: 'POST',
                body: formData,
            });
            const data = await response.json();
            showResult(data);
        } catch (err) {
            showResult({ result: 'ERROR', message: 'Network error: ' + err.message });
        } finally {
            processingOverlay.style.display = 'none';
        }
    }

    // ── Render Result ──
    function showResult(data) {
        cameraView.style.display = 'none';
        resultView.style.display = 'flex';

        let html = '';

        switch (data.result) {
            case 'MATCHED':
                html = `
                    <div class="gate-result-card result-matched p-4">
                        <div class="result-icon">✅</div>
                        <h1 class="result-title">MATCH</h1>
                        <div class="pass-badge-large">${esc(data.pass_number)}</div>
                        <h3 class="mt-3 text-white">${esc(data.name)}</h3>
                        <p class="similarity-badge">${data.similarity}% match</p>
                        ${data.customer_photo_url ? `<img src="${esc(data.customer_photo_url)}" class="result-photo" alt="Registered">` : ''}
                        <p class="text-muted mt-2">${esc(data.timestamp || '')}</p>
                        <button class="btn btn-navratri btn-lg w-100 mt-3" onclick="confirmEntry('${esc(data.entry_id)}')">
                            <i class="bi bi-check-circle-fill me-2"></i>Confirm Entry
                        </button>
                        <div class="auto-reset-bar"></div>
                    </div>`;
                break;

            case 'NO_MATCH':
                html = `
                    <div class="gate-result-card result-no-match p-4">
                        <div class="result-icon">❌</div>
                        <h1 class="result-title">NO MATCH</h1>
                        <p class="result-message">${esc(data.message)}</p>
                        ${data.best_score ? `<p class="text-muted">Best score: ${data.best_score}%</p>` : ''}
                        <button class="btn btn-outline-light btn-lg w-100 mt-3" onclick="resetGate()">
                            <i class="bi bi-arrow-repeat me-2"></i>Try Again
                        </button>
                        <div class="auto-reset-bar"></div>
                    </div>`;
                break;

            case 'DUPLICATE':
                html = `
                    <div class="gate-result-card result-duplicate p-4">
                        <div class="result-icon">⚠️</div>
                        <h1 class="result-title">ALREADY ENTERED</h1>
                        <div class="pass-badge-large">${esc(data.pass_number)}</div>
                        <h3 class="mt-3 text-white">${esc(data.name)}</h3>
                        <p class="result-message mt-2">${esc(data.message)}</p>
                        ${data.customer_photo_url ? `<img src="${esc(data.customer_photo_url)}" class="result-photo" alt="Registered">` : ''}
                        <button class="btn btn-outline-light btn-lg w-100 mt-3" onclick="resetGate()">
                            <i class="bi bi-arrow-repeat me-2"></i>Next Person
                        </button>
                        <div class="auto-reset-bar"></div>
                    </div>`;
                break;

            case 'BLOCKED':
                html = `
                    <div class="gate-result-card result-blocked p-4">
                        <div class="result-icon">🚫</div>
                        <h1 class="result-title">BLOCKED</h1>
                        <div class="pass-badge-large">${esc(data.pass_number)}</div>
                        <h3 class="mt-3 text-white">${esc(data.name)}</h3>
                        <p class="result-message mt-2">${esc(data.message)}</p>
                        <button class="btn btn-outline-light btn-lg w-100 mt-3" onclick="resetGate()">
                            <i class="bi bi-arrow-repeat me-2"></i>Next Person
                        </button>
                        <div class="auto-reset-bar"></div>
                    </div>`;
                break;

            case 'REVIEW':
                let candidatesHtml = '';
                if (data.candidates && data.candidates.length > 0) {
                    data.candidates.forEach(c => {
                        candidatesHtml += `
                            <div class="candidate-card" onclick="manualMatch('${esc(c.pass_id)}', '${esc(data.entry_id)}')">
                                ${c.customer_photo_url ? `<img src="${esc(c.customer_photo_url)}" class="candidate-photo" alt="">` : '<div class="candidate-photo bg-secondary"></div>'}
                                <div class="candidate-info">
                                    <div class="candidate-name">${esc(c.name)}</div>
                                    <div class="candidate-pass">${esc(c.pass_number)}</div>
                                    <div class="candidate-score">${c.similarity}% match</div>
                                </div>
                            </div>`;
                    });
                }
                html = `
                    <div class="gate-result-card result-review p-4">
                        <div class="result-icon">🔍</div>
                        <h1 class="result-title">REVIEW</h1>
                        <p class="result-message mb-3">${esc(data.message)}</p>
                        ${candidatesHtml}
                        <button class="btn btn-outline-light btn-lg w-100 mt-3" onclick="resetGate()">
                            <i class="bi bi-x-circle me-2"></i>No Match — Next Person
                        </button>
                    </div>`;
                break;

            case 'ERROR':
            default:
                html = `
                    <div class="gate-result-card result-error p-4">
                        <div class="result-icon">⚠️</div>
                        <h1 class="result-title">ERROR</h1>
                        <p class="result-message">${esc(data.message || 'Unknown error')}</p>
                        <button class="btn btn-outline-light btn-lg w-100 mt-3" onclick="resetGate()">
                            <i class="bi bi-arrow-repeat me-2"></i>Try Again
                        </button>
                    </div>`;
        }

        resultView.innerHTML = html;

        // Auto-reset after 6 seconds (except for REVIEW which needs manual action)
        if (data.result !== 'REVIEW') {
            clearTimeout(autoResetTimer);
            autoResetTimer = setTimeout(resetGate, 6000);
        }
    }

    // ── Confirm Entry ──
    window.confirmEntry = async function (entryId) {
        try {
            const formData = new FormData();
            formData.append('entry_id', entryId);
            formData.append('key', gateKey);

            const res = await fetch('confirm/', { method: 'POST', body: formData });
            const data = await res.json();

            if (data.status === 'ok') {
                // Flash green and reset
                resultView.querySelector('.gate-result-card').style.boxShadow =
                    '0 0 100px rgba(0, 230, 118, 0.5)';
                setTimeout(resetGate, 1500);
            }
        } catch (err) {
            console.error('Confirm error:', err);
        }
    };

    // ── Manual Match (REVIEW zone) ──
    window.manualMatch = async function (passId, entryId) {
        try {
            const formData = new FormData();
            formData.append('pass_id', passId);
            formData.append('entry_id', entryId);
            formData.append('key', gateKey);

            const res = await fetch('manual-match/', { method: 'POST', body: formData });
            const data = await res.json();

            if (data.status === 'ok') {
                showResult({
                    result: 'MATCHED',
                    pass_number: data.pass_number,
                    name: 'Manual Match',
                    similarity: 100,
                    entry_id: entryId,
                });
            }
        } catch (err) {
            console.error('Manual match error:', err);
        }
    };

    // ── Reset Gate ──
    window.resetGate = function () {
        clearTimeout(autoResetTimer);
        resultView.style.display = 'none';
        resultView.innerHTML = '';
        cameraView.style.display = 'flex';
    };

    // ── Escape HTML ──
    function esc(str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    // ── Init ──
    startCamera();

})();
