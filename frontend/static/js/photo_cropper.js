/* Кадрирование фото участника: масштаб и сдвиг, на выходе квадрат.
 *
 * Игроков часто снимают в полный рост — в кружке аватара лицо получается крошечным.
 * Окно даёт приблизить лицо до загрузки. Работает и в админке, и в форме тренера,
 * поэтому стили встроены сюда же.
 *
 *   const file = await PhotoCropper.crop(fileOrUrl);  // File или null, если «Отмена»
 *   PhotoCropper.replaceInputFile(input, file);       // подменить выбранный файл в <input type=file>
 */
(() => {
    const OUTPUT_SIZE = 800;
    const MAX_ZOOM = 5;

    const STYLE = `
        .pc-overlay { position: fixed; inset: 0; z-index: 5000; display: grid; place-items: center;
            padding: 16px; background: rgba(16, 18, 22, .62); backdrop-filter: blur(4px); }
        .pc-dialog { width: min(420px, 100%); padding: 18px; border-radius: 18px; background: #fff;
            box-shadow: 0 30px 90px rgba(10, 12, 16, .3); font-family: inherit; color: #25282d; }
        .pc-dialog h3 { margin: 0 0 4px; font-size: 17px; }
        .pc-dialog p { margin: 0 0 14px; color: #7a808a; font-size: 12.5px; line-height: 1.4; }
        .pc-stage { position: relative; width: min(340px, 100%); aspect-ratio: 1; margin: 0 auto;
            overflow: hidden; border-radius: 14px; background: #f1f2f4; cursor: grab;
            touch-action: none; user-select: none; }
        .pc-stage.dragging { cursor: grabbing; }
        .pc-stage img { position: absolute; top: 0; left: 0; max-width: none; transform-origin: 0 0;
            pointer-events: none; }
        .pc-stage::after { content: ''; position: absolute; inset: 0; border-radius: 50%;
            box-shadow: 0 0 0 999px rgba(255, 255, 255, .45); outline: 2px solid rgba(255, 255, 255, .9);
            pointer-events: none; }
        .pc-zoom { display: flex; align-items: center; gap: 10px; margin: 14px 0 4px; color: #7a808a;
            font-size: 18px; }
        .pc-zoom input { flex: 1; accent-color: #f07800; }
        .pc-actions { display: flex; justify-content: flex-end; gap: 8px; margin-top: 14px; }
        .pc-actions button { min-height: 40px; padding: 0 18px; border-radius: 11px; font: inherit;
            font-size: 14px; font-weight: 600; cursor: pointer; }
        .pc-cancel { border: 1px solid #dfe1e5; background: #fff; color: #444a54; }
        .pc-done { border: 0; background: #f07800; color: #fff; }
    `;

    function injectStyle() {
        if (document.getElementById('photoCropperStyle')) return;
        const style = document.createElement('style');
        style.id = 'photoCropperStyle';
        style.textContent = STYLE;
        document.head.appendChild(style);
    }

    function loadImage(src) {
        return new Promise((resolve, reject) => {
            const img = new Image();
            img.onload = () => resolve(img);
            img.onerror = reject;
            img.src = src;
        });
    }

    function baseName(source) {
        const name = source instanceof File ? source.name : String(source).split('/').pop().split('?')[0];
        return `${(name || 'photo').replace(/\.[^.]+$/, '') || 'photo'}.jpg`;
    }

    async function crop(source) {
        injectStyle();
        const objectUrl = source instanceof Blob ? URL.createObjectURL(source) : null;
        let img;
        try {
            img = await loadImage(objectUrl || source);
        } catch (error) {
            // Формат, который браузер не открывает (например, HEIC), — грузим как есть.
            if (objectUrl) URL.revokeObjectURL(objectUrl);
            return source instanceof File ? source : null;
        }

        const overlay = document.createElement('div');
        overlay.className = 'pc-overlay';
        overlay.innerHTML = `
            <div class="pc-dialog" role="dialog" aria-modal="true" aria-label="Кадр фото">
                <h3>Кадр фото</h3>
                <p>Приблизьте лицо ползунком и передвиньте фото пальцем или мышью. В кружок попадёт то, что внутри.</p>
                <div class="pc-stage"></div>
                <label class="pc-zoom"><span aria-hidden="true">−</span>
                    <input type="range" min="1" max="${MAX_ZOOM}" step="0.01" value="1" aria-label="Масштаб">
                    <span aria-hidden="true">+</span></label>
                <div class="pc-actions">
                    <button type="button" class="pc-cancel">Отмена</button>
                    <button type="button" class="pc-done">Готово</button>
                </div>
            </div>`;
        const stage = overlay.querySelector('.pc-stage');
        const range = overlay.querySelector('input[type="range"]');
        stage.appendChild(img);
        document.body.appendChild(overlay);

        const view = { size: 0, base: 1, zoom: 1, x: 0, y: 0 };
        const scale = () => view.base * view.zoom;

        function clamp() {
            const width = img.naturalWidth * scale();
            const height = img.naturalHeight * scale();
            view.x = Math.min(0, Math.max(view.size - width, view.x));
            view.y = Math.min(0, Math.max(view.size - height, view.y));
        }

        function draw() {
            clamp();
            img.style.transform = `translate(${view.x}px, ${view.y}px) scale(${scale()})`;
        }

        // Масштаб вокруг точки (по умолчанию — центр окна), чтобы лицо не уезжало.
        function setZoom(value, pointX = view.size / 2, pointY = view.size / 2) {
            const zoom = Math.max(1, Math.min(MAX_ZOOM, value));
            const imageX = (pointX - view.x) / scale();
            const imageY = (pointY - view.y) / scale();
            view.zoom = zoom;
            view.x = pointX - imageX * scale();
            view.y = pointY - imageY * scale();
            range.value = String(zoom);
            draw();
        }

        function layout() {
            const previous = view.size;
            view.size = stage.clientWidth;
            view.base = Math.max(view.size / img.naturalWidth, view.size / img.naturalHeight);
            if (!previous) {
                // Портрет в полный рост: лицо обычно сверху — начинаем с верхней части кадра.
                view.x = (view.size - img.naturalWidth * scale()) / 2;
                view.y = img.naturalHeight > img.naturalWidth * 1.15 ? 0
                    : (view.size - img.naturalHeight * scale()) / 2;
            }
            draw();
        }
        layout();

        let drag = null;
        stage.addEventListener('pointerdown', (event) => {
            drag = { id: event.pointerId, x: event.clientX, y: event.clientY, startX: view.x, startY: view.y };
            stage.setPointerCapture(event.pointerId);
            stage.classList.add('dragging');
        });
        stage.addEventListener('pointermove', (event) => {
            if (!drag || drag.id !== event.pointerId) return;
            view.x = drag.startX + event.clientX - drag.x;
            view.y = drag.startY + event.clientY - drag.y;
            draw();
        });
        const endDrag = () => {
            drag = null;
            stage.classList.remove('dragging');
        };
        stage.addEventListener('pointerup', endDrag);
        stage.addEventListener('pointercancel', endDrag);
        stage.addEventListener('wheel', (event) => {
            event.preventDefault();
            const rect = stage.getBoundingClientRect();
            setZoom(view.zoom * (event.deltaY < 0 ? 1.08 : 1 / 1.08),
                event.clientX - rect.left, event.clientY - rect.top);
        }, { passive: false });
        range.addEventListener('input', () => setZoom(Number(range.value)));
        window.addEventListener('resize', layout);

        return new Promise((resolve) => {
            function close(result) {
                window.removeEventListener('resize', layout);
                document.removeEventListener('keydown', onKey, true);
                overlay.remove();
                if (objectUrl) URL.revokeObjectURL(objectUrl);
                resolve(result);
            }
            function onKey(event) {
                if (event.key === 'Escape') {
                    event.stopPropagation();
                    close(null);
                }
            }
            document.addEventListener('keydown', onKey, true);
            overlay.querySelector('.pc-cancel').addEventListener('click', () => close(null));
            overlay.querySelector('.pc-done').addEventListener('click', () => {
                const canvas = document.createElement('canvas');
                const side = Math.min(OUTPUT_SIZE, Math.round(view.size / scale()));
                canvas.width = side;
                canvas.height = side;
                const ctx = canvas.getContext('2d');
                ctx.fillStyle = '#fff';
                ctx.fillRect(0, 0, side, side);
                ctx.imageSmoothingQuality = 'high';
                ctx.drawImage(img, -view.x / scale(), -view.y / scale(), view.size / scale(),
                    view.size / scale(), 0, 0, side, side);
                canvas.toBlob((blob) => {
                    close(blob ? new File([blob], baseName(source), { type: 'image/jpeg' }) : null);
                }, 'image/jpeg', 0.9);
            });
        });
    }

    function replaceInputFile(input, file) {
        const transfer = new DataTransfer();
        if (file) transfer.items.add(file);
        input.files = transfer.files;
    }

    window.PhotoCropper = { crop, replaceInputFile };
})();
