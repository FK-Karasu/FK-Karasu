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
        ['theme.accent', 'Основной цвет', 'color', '#ff8a00'],
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
        panel.querySelector('input, textarea').focus();
    }

    function applySettings() {
        const panel = document.getElementById('edSettings');
        panel.querySelectorAll('[data-setting]').forEach((field) => {
            const value = field.value.trim();
            if (field.dataset.type === 'lines') {
                setAt(field.dataset.setting, value.split('\n').map((line) => line.trim()).filter(Boolean));
            } else if (field.dataset.setting === 'contact.whatsapp') {
                setAt(field.dataset.setting, value.replace(/\D/g, ''));
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

    function bindToolbar() {
        document.getElementById('edPublish').addEventListener('click', publish);
        document.getElementById('edDiscard').addEventListener('click', discard);
        document.getElementById('edOpenSettings').addEventListener('click', openSettings);
        document.getElementById('edSettings').addEventListener('click', (event) => {
            const action = event.target.closest('[data-settings]')?.dataset.settings;
            if (action === 'cancel' || event.target.id === 'edSettings') event.currentTarget.hidden = true;
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
