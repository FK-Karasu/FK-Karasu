/* Конструктор страницы KARASU EVENT.
 *
 * Страница показывается как у гостя, но тексты редактируются прямо на ней,
 * фото меняются кликом, списки пополняются кнопками «+». Всё пишется в черновик
 * (автосохранение), гости видят изменения только после «Опубликовать».
 */
(() => {
    const source = document.getElementById('eventContent');
    if (!source) return;
    let state = JSON.parse(source.textContent);
    let saveTimer = null;
    let dirty = false;
    let saving = false;

    const SCROLL_KEY = 'eventEditorScroll';
    const NEW_ITEMS = {
        text: () => 'Новый пункт',
        stat: () => ({ value: '0', label: 'подпись' }),
        variant: () => ({
            name: 'Новый вариант', tag: '', price: '0$', unit: 'сутки',
            features: ['Номера на 2 человека'], photos: [],
        }),
        photo: () => ({ image: 'img/event/v1-field.webp', caption: 'Подпись к фото' }),
        block: () => ({
            eyebrow: 'Новый раздел', title: 'ЗАГОЛОВОК БЛОКА',
            text: 'Текст блока: расскажите, что здесь важно для гостей.',
            items: [], photos: [], style: 'dark',
        }),
    };

    /* --- Путь вида «stay.variants.1.features.2» --- */

    function parts(path) {
        return path.split('.').map((part) => (/^\d+$/.test(part) ? Number(part) : part));
    }

    function getAt(path) {
        return parts(path).reduce((node, key) => (node == null ? node : node[key]), state);
    }

    function setAt(path, value) {
        const keys = parts(path);
        const last = keys.pop();
        let node = state;
        keys.forEach((key, index) => {
            if (node[key] == null) node[key] = typeof keys[index + 1] === 'number' || typeof last === 'number' ? [] : {};
            node = node[key];
        });
        node[last] = value;
    }

    /* --- Сохранение --- */

    function setStatus(text, kind = '') {
        const status = document.getElementById('edStatus');
        status.textContent = text;
        status.className = `ed-status ${kind}`;
    }

    async function send(payload) {
        const response = await fetch('/api/event-page', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) throw new Error(data.message || 'Не удалось сохранить');
        return data;
    }

    async function saveDraft() {
        window.clearTimeout(saveTimer);
        if (saving) return;
        saving = true;
        setStatus('Сохраняем…');
        try {
            const data = await send({ content: state });
            dirty = false;
            setStatus(data.has_changes ? 'Черновик сохранён · не опубликован' : 'Опубликовано', data.has_changes ? 'draft' : 'ok');
        } catch (error) {
            setStatus(error.message, 'error');
        } finally {
            saving = false;
        }
    }

    function scheduleSave() {
        dirty = true;
        setStatus('Есть несохранённые правки', 'draft');
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(saveDraft, 1200);
    }

    async function saveAndReload() {
        await saveDraft();
        try {
            window.sessionStorage.setItem(SCROLL_KEY, String(window.scrollY));
        } catch (error) { /* без памяти прокрутки */ }
        window.location.reload();
    }

    async function publish() {
        const button = document.getElementById('edPublish');
        button.disabled = true;
        setStatus('Публикуем…');
        try {
            await send({ content: state, publish: true });
            dirty = false;
            setStatus('Опубликовано — гости уже видят изменения', 'ok');
        } catch (error) {
            setStatus(error.message, 'error');
        } finally {
            button.disabled = false;
        }
    }

    async function discard() {
        if (!window.confirm('Отменить все неопубликованные правки и вернуть то, что сейчас видят гости?')) return;
        await send({ discard: true });
        window.location.reload();
    }

    /* --- Тексты --- */

    function bindTexts() {
        document.querySelectorAll('[data-edit]').forEach((el) => {
            try {
                el.contentEditable = 'plaintext-only';
            } catch (error) {
                el.contentEditable = 'true';
            }
            if (el.contentEditable !== 'plaintext-only') el.contentEditable = 'true';
            el.spellcheck = true;
            el.addEventListener('input', () => {
                setAt(el.dataset.edit, el.innerText.replace(/\n{3,}/g, '\n\n').trim());
                scheduleSave();
            });
            el.addEventListener('keydown', (event) => {
                // Enter в однострочных полях — просто закончить правку.
                if (event.key === 'Enter' && !['P'].includes(el.tagName)) {
                    event.preventDefault();
                    el.blur();
                }
            });
            el.addEventListener('paste', (event) => {
                event.preventDefault();
                const text = (event.clipboardData || window.clipboardData).getData('text/plain');
                document.execCommand('insertText', false, text);
            });
        });
    }

    /* --- Фото --- */

    async function uploadFile(file) {
        const form = new FormData();
        form.append('image', file);
        const response = await fetch('/api/event-page/upload', { method: 'POST', body: form });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || !data.success) throw new Error(data.message || 'Не удалось загрузить');
        return data;
    }

    // Сразу несколько фото — дописываем в конец списка по одному, чтобы видеть прогресс.
    function addPhotos(listPath) {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.multiple = true;
        input.addEventListener('change', async () => {
            const files = [...(input.files || [])];
            if (!files.length) return;
            if (!Array.isArray(getAt(listPath))) setAt(listPath, []);
            let done = 0;
            try {
                for (const file of files) {
                    setStatus(`Загружаем фото ${done + 1} из ${files.length}…`);
                    const data = await uploadFile(file);
                    getAt(listPath).push(data.path);
                    done += 1;
                }
            } catch (error) {
                setStatus(`${error.message} (загружено ${done} из ${files.length})`, 'error');
            }
            if (done) await saveAndReload();
        });
        input.click();
    }

    function moveItem(listPath, index, dir) {
        const list = getAt(listPath);
        const to = index + dir;
        if (!Array.isArray(list) || to < 0 || to >= list.length) return;
        [list[index], list[to]] = [list[to], list[index]];
        saveAndReload();
    }

    function toggleStyle(blockPath) {
        const block = getAt(blockPath);
        block.style = block.style === 'light' ? 'dark' : 'light';
        saveAndReload();
    }

    function pickImage(path, target) {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = 'image/*';
        input.addEventListener('change', async () => {
            const file = input.files && input.files[0];
            if (!file) return;
            const form = new FormData();
            form.append('image', file);
            setStatus('Загружаем фото…');
            try {
                const response = await fetch('/api/event-page/upload', { method: 'POST', body: form });
                const data = await response.json();
                if (!data.success) throw new Error(data.message || 'Не удалось загрузить');
                setAt(path, data.path);
                if (target.tagName === 'IMG') {
                    target.src = data.url;
                    scheduleSave();
                } else {
                    await saveAndReload();
                }
            } catch (error) {
                setStatus(error.message, 'error');
            }
        });
        input.click();
    }

    /* --- Списки --- */

    function removeItem(listPath, index) {
        const list = getAt(listPath);
        if (!Array.isArray(list)) return;
        if (listPath === 'stay.variants' && !window.confirm('Убрать этот вариант проживания со страницы?')) return;
        if (listPath === 'blocks' && !window.confirm('Удалить этот блок со страницы?')) return;
        list.splice(index, 1);
        saveAndReload();
    }

    function addItem(listPath, kind) {
        let list = getAt(listPath);
        if (!Array.isArray(list)) {
            setAt(listPath, []);
            list = getAt(listPath);
        }
        list.push((NEW_ITEMS[kind] || NEW_ITEMS.text)());
        saveAndReload();
    }

    function cycleSize(itemPath) {
        const order = ['', 'wide', 'tall'];
        const item = getAt(itemPath);
        item.size = order[(order.indexOf(item.size || '') + 1) % order.length];
        saveAndReload();
    }

    /* --- Настройки: контакты, SEO, цвет, бегущая строка --- */

    const SETTINGS = [
        ['contact.phone', 'Телефон', 'text', '+998 90 000 00 00'],
        ['contact.whatsapp', 'WhatsApp (только цифры)', 'text', '998900000000'],
        ['contact.telegram', 'Telegram (без @)', 'text', 'username'],
        ['contact.instagram', 'Instagram (без @)', 'text', 'необязательно'],
        ['contact.contact_name', 'Контактное лицо', 'text', 'Имя'],
        ['theme.accent', 'Основной цвет страницы', 'palette', '#ff8a00'],
        ['marquee', 'Бегущая строка — по одному слову в строке', 'lines', ''],
        ['meta.title', 'Заголовок вкладки браузера (SEO)', 'text', ''],
        ['meta.description', 'Описание для поисковиков и ссылок в мессенджерах', 'textarea', ''],
    ];

    function openSettings() {
        const panel = document.getElementById('edSettings');
        panel.innerHTML = `
            <div class="ed-settings-box" role="dialog" aria-modal="true" aria-labelledby="edSettingsTitle">
                <h3 id="edSettingsTitle">Настройки страницы</h3>
                ${SETTINGS.map(([path, label, type, placeholder]) => {
                    const value = getAt(path);
                    const text = Array.isArray(value) ? value.join('\n') : (value || '');
                    if (type === 'palette') return paletteField(path, label, text || placeholder);
                    const field = type === 'textarea' || type === 'lines'
                        ? `<textarea rows="${type === 'lines' ? 5 : 3}" data-setting="${path}" data-type="${type}"
                            placeholder="${placeholder}">${escapeHtml(text)}</textarea>`
                        : `<input type="${type}" data-setting="${path}" data-type="${type}" placeholder="${placeholder}"
                            value="${escapeHtml(text || (type === 'color' ? '#ff8a00' : ''))}">`;
                    return `<label><span>${label}</span>${field}</label>`;
                }).join('')}
                <div class="ed-settings-actions">
                    <button type="button" class="ed-btn ghost" data-settings="cancel">Отмена</button>
                    <button type="button" class="ed-btn" data-settings="apply">Применить</button>
                </div>
            </div>`;
        panel.hidden = false;
        bindPalette(panel);
        panel.querySelector('input:not([type=color]), textarea').focus();
    }

    /* --- Палитра основного цвета --- */

    const DEFAULT_ACCENT = '#ff8a00';
    const PALETTE_HUES = [0, 12, 24, 33, 45, 55, 75, 100, 135, 160, 178, 192, 205, 218, 235, 255, 275, 295, 320, 340];
    const PALETTE_LIGHTS = [28, 38, 48, 58, 68];

    function hslToHex(h, s, l) {
        s /= 100; l /= 100;
        const k = (n) => (n + h / 30) % 12;
        const a = s * Math.min(l, 1 - l);
        const f = (n) => l - a * Math.max(-1, Math.min(k(n) - 3, Math.min(9 - k(n), 1)));
        return `#${[f(0), f(8), f(4)].map((x) => Math.round(x * 255).toString(16).padStart(2, '0')).join('')}`;
    }

    // 20 оттенков × 5 яркостей + серые = 108 готовых цветов, как палитра в Excel.
    function paletteColors() {
        const rows = PALETTE_LIGHTS.map((l) => PALETTE_HUES.map((h) => hslToHex(h, l >= 58 ? 88 : 92, l)));
        rows.unshift(['#ff8a00', '#e30613', '#16a34a', '#2563eb', '#7c3aed', '#db2777', '#0891b2', '#ca8a04']
            .concat(['#111827', '#374151', '#6b7280', '#9ca3af', '#d1d5db', '#f3f4f6', '#ffffff', '#facc15', '#84cc16', '#14b8a6', '#0ea5e9', '#f97316']));
        return rows;
    }

    function inkFor(hex) {
        const ch = (i) => {
            const v = parseInt(hex.slice(i, i + 2), 16) / 255;
            return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4;
        };
        const lum = 0.2126 * ch(1) + 0.7152 * ch(3) + 0.0722 * ch(5);
        return (lum + 0.05) / 0.05 >= 1.05 / (lum + 0.05) ? '#14110d' : '#ffffff';
    }

    // Пока окно открыто, вся страница сразу перекрашивается — видно, как будет.
    function previewAccent(hex) {
        const root = document.documentElement.style;
        root.setProperty('--accent-custom', hex);
        root.setProperty('--accent-ink-custom', inkFor(hex));
    }

    function paletteField(path, label, current) {
        const rows = paletteColors();
        const swatch = (hex) => `<button type="button" class="ed-swatch${hex === current.toLowerCase() ? ' on' : ''}"
            data-color="${hex}" style="background:${hex}" title="${hex}" aria-label="Цвет ${hex}"></button>`;
        return `<div class="ed-palette-field"><span>${label}</span>
            <div class="ed-palette">
                <div class="ed-palette-row ed-palette-base">${rows[0].map(swatch).join('')}</div>
                ${rows.slice(1).map((row) => `<div class="ed-palette-row">${row.map(swatch).join('')}</div>`).join('')}
            </div>
            <div class="ed-palette-own">
                <span class="ed-palette-preview" style="background:${current};color:${inkFor(current)}">Кнопка</span>
                <label>Свой цвет <input type="color" value="${current}" data-palette-picker></label>
                <input type="text" value="${current}" maxlength="7" data-setting="${path}" data-type="palette" spellcheck="false">
                <button type="button" class="ed-btn ghost" data-palette-reset>Как было (оранжевый)</button>
            </div></div>`;
    }

    function bindPalette(panel) {
        const field = panel.querySelector('[data-type="palette"]');
        if (!field) return;
        const picker = panel.querySelector('[data-palette-picker]');
        const preview = panel.querySelector('.ed-palette-preview');
        const choose = (hex) => {
            if (!/^#[0-9a-f]{6}$/i.test(hex)) return;
            hex = hex.toLowerCase();
            field.value = hex;
            picker.value = hex;
            preview.style.background = hex;
            preview.style.color = inkFor(hex);
            panel.querySelectorAll('.ed-swatch').forEach((b) => b.classList.toggle('on', b.dataset.color === hex));
            previewAccent(hex);
        };
        panel.addEventListener('click', (event) => {
            const sw = event.target.closest('.ed-swatch');
            if (sw) choose(sw.dataset.color);
            if (event.target.closest('[data-palette-reset]')) choose(DEFAULT_ACCENT);
        });
        picker.addEventListener('input', () => choose(picker.value));
        field.addEventListener('input', () => choose(field.value.startsWith('#') ? field.value : `#${field.value}`));
    }

    function restoreAccent() {
        const hex = getAt('theme.accent');
        if (/^#[0-9a-f]{6}$/i.test(hex || '')) previewAccent(hex);
        else {
            document.documentElement.style.removeProperty('--accent-custom');
            document.documentElement.style.removeProperty('--accent-ink-custom');
        }
    }

    function applySettings() {
        const panel = document.getElementById('edSettings');
        panel.querySelectorAll('[data-setting]').forEach((field) => {
            const value = field.value.trim();
            if (field.dataset.type === 'lines') {
                setAt(field.dataset.setting, value.split('\n').map((line) => line.trim()).filter(Boolean));
            } else if (field.dataset.setting === 'contact.whatsapp') {
                setAt(field.dataset.setting, value.replace(/\D/g, ''));
            } else if (field.dataset.type === 'palette') {
                if (/^#[0-9a-f]{6}$/i.test(value)) setAt(field.dataset.setting, value.toLowerCase());
            } else if (['contact.telegram', 'contact.instagram'].includes(field.dataset.setting)) {
                setAt(field.dataset.setting, value.replace(/^@/, ''));
            } else {
                setAt(field.dataset.setting, value);
            }
        });
        panel.hidden = true;
        saveAndReload();
    }

    function escapeHtml(value) {
        return String(value ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
    }

    /* --- Панель и события --- */

    function adminBackUrl(fallback) {
        // Возвращаемся туда, откуда пришли в админке; со страницы гостя или по прямой ссылке — на главную.
        try {
            const from = new URL(document.referrer);
            if (from.origin === window.location.origin && !from.pathname.startsWith('/event')) return from.href;
        } catch (error) { /* нет referrer */ }
        return fallback;
    }

    async function goBack(event) {
        event.preventDefault();
        const target = adminBackUrl(event.currentTarget.href);
        if (dirty) await saveDraft();
        dirty = false;
        window.location.href = target;
    }

    function bindToolbar() {
        document.getElementById('edBack').addEventListener('click', goBack);
        document.getElementById('edPublish').addEventListener('click', publish);
        document.getElementById('edDiscard').addEventListener('click', discard);
        document.getElementById('edOpenSettings').addEventListener('click', openSettings);
        document.getElementById('edSettings').addEventListener('click', (event) => {
            const action = event.target.closest('[data-settings]')?.dataset.settings;
            if (action === 'cancel' || event.target.id === 'edSettings') {
                event.currentTarget.hidden = true;
                restoreAccent();
            }
            if (action === 'apply') applySettings();
        });
    }

    document.addEventListener('click', (event) => {
        const imageTarget = event.target.closest('[data-edit-img]');
        if (imageTarget) {
            event.preventDefault();
            event.stopPropagation();
            pickImage(imageTarget.dataset.editImg, imageTarget);
            return;
        }
        const remove = event.target.closest('[data-ed-remove]');
        if (remove) {
            event.preventDefault();
            event.stopPropagation();
            removeItem(remove.dataset.edRemove, Number(remove.dataset.index));
            return;
        }
        const add = event.target.closest('[data-ed-add]');
        if (add) {
            event.preventDefault();
            addItem(add.dataset.edAdd, add.dataset.kind);
            return;
        }
        const photosAdd = event.target.closest('[data-ed-photos-add]');
        if (photosAdd) {
            event.preventDefault();
            event.stopPropagation();
            addPhotos(photosAdd.dataset.edPhotosAdd);
            return;
        }
        const move = event.target.closest('[data-ed-move]');
        if (move) {
            event.preventDefault();
            event.stopPropagation();
            moveItem(move.dataset.edMove, Number(move.dataset.index), Number(move.dataset.dir));
            return;
        }
        const style = event.target.closest('[data-ed-style]');
        if (style) {
            event.preventDefault();
            event.stopPropagation();
            toggleStyle(style.dataset.edStyle);
            return;
        }
        const size = event.target.closest('[data-ed-size]');
        if (size) {
            event.preventDefault();
            event.stopPropagation();
            cycleSize(size.dataset.edSize);
            return;
        }
        // В редакторе ссылки и кнопки не уводят со страницы, а дают править текст.
        if (event.target.closest('[data-edit]') || event.target.closest('a[href]:not(.ed-btn)')) {
            if (!event.target.closest('.ed-toolbar')) event.preventDefault();
        }
    }, true);

    window.addEventListener('beforeunload', (event) => {
        if (dirty) {
            event.preventDefault();
            event.returnValue = '';
        }
    });

    bindTexts();
    bindToolbar();
    document.querySelectorAll('.reveal').forEach((el) => el.classList.add('in'));
    try {
        const y = Number(window.sessionStorage.getItem(SCROLL_KEY));
        window.sessionStorage.removeItem(SCROLL_KEY);
        if (y) window.scrollTo(0, y);
    } catch (error) { /* ничего */ }
    setStatus(document.body.dataset.hasChanges === '1' ? 'Черновик · не опубликован' : 'Опубликовано',
        document.body.dataset.hasChanges === '1' ? 'draft' : 'ok');
})();
