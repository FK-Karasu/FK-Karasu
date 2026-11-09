// settings.js updated: FORCE REBUILD 2
document.addEventListener('DOMContentLoaded', initSettings);
let expenseCategories = [];
let bridgeStatusTimer = null;
let lastBridgeProgress = null;
let settingsDirtyTrackingReady = false;
const settingsFormSnapshots = new Map();
const ACCESS_POLICY_INFO = {
    full_current_month: {
        title: 'Только 100% оплата текущего месяца',
        short: 'Пропускаем только если текущий месяц оплачен полностью.',
        details: 'Ученик проходит через терминал только после 100% оплаты текущего месяца. Частичная оплата текущего месяца не допускает к проходу.',
        example: 'Пример: тариф 500 000, оплачено 250 000 за июль - проход закрыт. Оплачено 500 000 - проход открыт.'
    },
    partial_current_month: {
        title: 'Частичная оплата текущего месяца, без старых долгов',
        short: 'Нужна любая оплата за текущий месяц, старых долгов быть не должно.',
        details: 'Ученик проходит, если за текущий месяц есть оплата. Долги за прошлые месяцы блокируют проход.',
        example: 'Пример: за июль оплачено 100 000 и старых долгов нет - проход открыт. Есть долг за июнь - проход закрыт.'
    },
    any_payment_this_month: {
        title: 'Частичная оплата текущего месяца, разрешить старые долги',
        short: 'Нужна оплата за текущий месяц, старые долги разрешены в пределах лимита.',
        details: 'Ученик проходит, если за текущий месяц есть оплата, а старый долг не превышает выбранное количество месяцев.',
        example: 'Пример: лимит 1 месяц, есть долг за июнь и оплата за июль - проход открыт. Долг за май и июнь - проход закрыт.'
    }
};
let paymentProviderConfigs = {};
const PAYMENT_PROVIDER_DEFINITIONS = [
    {
        id: 'payme',
        title: 'Payme',
        logo: '/static/uploads/payme.png',
        docsUrl: 'https://developer.help.paycom.uz/',
        note: 'Merchant API: JSON-RPC callback с CheckPerformTransaction, CreateTransaction, PerformTransaction, CancelTransaction.',
        example: 'Sandbox: merchant_id + secret/test key. Account key обычно student_id или payment_id.',
        fields: [
            { key: 'merchant_id', label: 'Merchant ID', placeholder: 'ID кассы Payme' },
            { key: 'login', label: 'Login', placeholder: 'Paycom login' },
            { key: 'secret_key', label: 'Secret / test key', placeholder: 'Ключ кассы', type: 'password', wide: true },
            { key: 'account_key', label: 'Account field', placeholder: 'student_id или payment_id' },
            { key: 'checkout_url', label: 'Pay URL', placeholder: 'https://checkout.paycom.uz/...' },
            { key: 'callback_url', label: 'Callback URL', placeholder: '/api/payments/payme/callback', wide: true },
            { key: 'test_amount', label: 'Тестовая сумма', placeholder: '1000' },
            { key: 'notes', label: 'Заметки', placeholder: 'Доступы/условия из кабинета Payme', wide: true }
        ]
    },
    {
        id: 'click',
        title: 'Click',
        logo: '/static/uploads/click.png',
        docsUrl: 'https://docs.click.uz/',
        note: 'Merchant Billing API: prepare/complete callback, service_id, merchant_id, merchant_user_id и secret_key.',
        example: 'Sandbox: проверьте sign_string и action 0/1 на тестовой оплате.',
        fields: [
            { key: 'merchant_id', label: 'Merchant ID', placeholder: 'merchant_id' },
            { key: 'service_id', label: 'Service ID', placeholder: 'service_id' },
            { key: 'merchant_user_id', label: 'Merchant user ID', placeholder: 'merchant_user_id' },
            { key: 'secret_key', label: 'Secret key', placeholder: 'secret_key', type: 'password', wide: true },
            { key: 'endpoint_url', label: 'Merchant endpoint', placeholder: 'https://api.click.uz/...' },
            { key: 'callback_url', label: 'Prepare/Complete URL', placeholder: '/api/payments/click/callback', wide: true },
            { key: 'test_amount', label: 'Тестовая сумма', placeholder: '1000' },
            { key: 'notes', label: 'Заметки', placeholder: 'Action 0/1, sign_string, параметры кабинета', wide: true }
        ]
    },
    {
        id: 'uzum',
        title: 'Uzum Bank',
        logo: '/static/uploads/uzum.png',
        docsUrl: 'https://developer.uzumbank.uz/',
        note: 'Подготовлено под Checkout/Merchant/Dynamic QR: ID мерчанта, сервис, секрет и callback.',
        example: 'После выдачи кабинета внесем точный endpoint песочницы и метод оплаты.',
        fields: [
            { key: 'merchant_id', label: 'Merchant ID', placeholder: 'ID мерчанта' },
            { key: 'service_id', label: 'Service / shop ID', placeholder: 'service_id или shop_id' },
            { key: 'cashbox_id', label: 'Terminal / cashbox ID', placeholder: 'terminal_id' },
            { key: 'secret_key', label: 'Secret key', placeholder: 'secret_key', type: 'password', wide: true },
            { key: 'token', label: 'Access token', placeholder: 'token', type: 'password', wide: true },
            { key: 'endpoint_url', label: 'API endpoint', placeholder: 'https://...' },
            { key: 'checkout_url', label: 'Checkout URL', placeholder: 'https://...' },
            { key: 'callback_url', label: 'Callback URL', placeholder: '/api/payments/uzum/callback', wide: true },
            { key: 'account_key', label: 'Account field', placeholder: 'student_id или payment_id' },
            { key: 'test_amount', label: 'Тестовая сумма', placeholder: '1000' },
            { key: 'notes', label: 'Заметки', placeholder: 'Что выдаст кабинет Uzum', wide: true }
        ]
    },
    {
        id: 'oson',
        title: 'OSON',
        logo: '/static/uploads/oson.jpeg',
        docsUrl: 'https://docs.oson.com/',
        note: 'Подготовлено под кассу/merchant account: cashbox/service ID, secret/token и callback статусов.',
        example: 'Для теста нужен ключ кассы и тестовый endpoint из кабинета OSON.',
        fields: [
            { key: 'merchant_id', label: 'Merchant ID', placeholder: 'merchant_id' },
            { key: 'service_id', label: 'Service ID', placeholder: 'service_id' },
            { key: 'cashbox_id', label: 'Cashbox ID', placeholder: 'cashbox_id' },
            { key: 'secret_key', label: 'Secret key', placeholder: 'secret_key', type: 'password', wide: true },
            { key: 'token', label: 'Token', placeholder: 'api token', type: 'password', wide: true },
            { key: 'endpoint_url', label: 'API endpoint', placeholder: 'https://...' },
            { key: 'callback_url', label: 'Callback URL', placeholder: '/api/payments/oson/callback', wide: true },
            { key: 'account_key', label: 'Account field', placeholder: 'student_id или payment_id' },
            { key: 'test_amount', label: 'Тестовая сумма', placeholder: '1000' },
            { key: 'notes', label: 'Заметки', placeholder: 'Касса, услуга, тестовые параметры', wide: true }
        ]
    },
    {
        id: 'paynet',
        title: 'Paynet',
        logo: '/static/uploads/paynet.png',
        docsUrl: 'https://github.com/PayTechUz/paynet-pkg',
        note: 'Подготовлено под узбекский Paynet: параметры агента/услуги, токен, endpoint и callback заполняются после договора.',
        example: 'Публичные примеры есть у PayTechUZ, production включайте только после выдачи официальных параметров Paynet Uzbekistan.',
        fields: [
            { key: 'agent_id', label: 'Agent ID', placeholder: 'agent_id' },
            { key: 'service_id', label: 'Service ID', placeholder: 'service_id' },
            { key: 'terminal_id', label: 'Terminal ID', placeholder: 'terminal_id' },
            { key: 'secret_key', label: 'Secret key', placeholder: 'secret_key', type: 'password', wide: true },
            { key: 'token', label: 'Token', placeholder: 'api token', type: 'password', wide: true },
            { key: 'endpoint_url', label: 'API endpoint', placeholder: 'https://...' },
            { key: 'callback_url', label: 'Callback URL', placeholder: '/api/payments/paynet/callback', wide: true },
            { key: 'account_key', label: 'Account field', placeholder: 'student_id или payment_id' },
            { key: 'test_amount', label: 'Тестовая сумма', placeholder: '1000' },
            { key: 'notes', label: 'Заметки', placeholder: 'Параметры от Paynet после договора', wide: true }
        ]
    },
    {
        id: 'multicard',
        title: 'Multicard',
        logo: '/static/uploads/multicard.png',
        docsUrl: 'https://docs.multicard.uz/introduction-4736405f0',
        note: 'Единая интеграция: sandbox/prod API, token на 24 часа, invoice checkout_url/short_link и webhook статуса.',
        example: 'Sandbox endpoint: https://dev-mesh.multicard.uz/. Production: https://mesh.multicard.uz/. Webhook sign: sha1(uuid + invoice_id + amount + secret).',
        fields: [
            { key: 'uuid', label: 'UUID', placeholder: 'uuid проекта/мерчанта' },
            { key: 'store_id', label: 'Store ID', placeholder: 'store_id' },
            { key: 'api_key', label: 'API key', placeholder: 'api key', type: 'password', wide: true },
            { key: 'secret_key', label: 'Webhook secret', placeholder: 'secret для sign', type: 'password', wide: true },
            { key: 'token', label: 'Bearer token', placeholder: 'токен на 24 часа', type: 'password', wide: true },
            { key: 'endpoint_url', label: 'API endpoint', placeholder: 'https://dev-mesh.multicard.uz/' },
            { key: 'checkout_url', label: 'Checkout URL', placeholder: 'checkout_url / short_link' },
            { key: 'callback_url', label: 'Webhook URL', placeholder: '/api/payments/multicard/callback', wide: true },
            { key: 'webhook_sign_formula', label: 'Webhook sign', placeholder: 'sha1(uuid + invoice_id + amount + secret)', wide: true },
            { key: 'test_amount', label: 'Тестовая сумма', placeholder: '1000' },
            { key: 'notes', label: 'Заметки', placeholder: 'Тестовая карта, OTP, статусные callbacks', wide: true }
        ]
    }
];

async function initSettings() {
    attachWorkingDayToggles();
    await loadSettings();
    attachAccessPaymentPolicyControls();

    const expenseInput = document.getElementById('expense-category-input');
    if (expenseInput) {
        expenseInput.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                addExpenseCategorySetting();
            }
        });
    }

    document.querySelectorAll('form.settings-form').forEach((settingsForm) => {
        if (!SETTINGS_FORM_KEYS[settingsForm.id]) return;
        settingsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            await saveSettingsForm(settingsForm);
        });
    });

    const uploadLogoBtn = document.getElementById('uploadLogoBtn');
    if (uploadLogoBtn) uploadLogoBtn.addEventListener('click', uploadSystemLogo);
    const logoFileInput = document.getElementById('system_logo_file');
    if (logoFileInput) {
        logoFileInput.addEventListener('change', () => {
            const fileName = document.getElementById('logo_file_name');
            if (fileName) fileName.textContent = logoFileInput.files?.[0]?.name || 'Файл не выбран';
            if (logoFileInput.files?.[0]) uploadSystemLogo();
        });
    }
    const resetLogoBtn = document.getElementById('resetLogoBtn');
    if (resetLogoBtn) resetLogoBtn.addEventListener('click', resetSystemLogo);
    const uploadSquareLogoBtn = document.getElementById('uploadSquareLogoBtn');
    if (uploadSquareLogoBtn) uploadSquareLogoBtn.addEventListener('click', uploadSystemSquareLogo);
    const squareLogoFileInput = document.getElementById('system_square_logo_file');
    if (squareLogoFileInput) {
        squareLogoFileInput.addEventListener('change', () => {
            const fileName = document.getElementById('square_logo_file_name');
            if (fileName) fileName.textContent = squareLogoFileInput.files?.[0]?.name || 'Файл не выбран';
            if (squareLogoFileInput.files?.[0]) uploadSystemSquareLogo();
        });
    }
    const resetSquareLogoBtn = document.getElementById('resetSquareLogoBtn');
    if (resetSquareLogoBtn) resetSquareLogoBtn.addEventListener('click', resetSystemSquareLogo);
    attachTemplateTokenButtons();
    // Секреты скрыты точками: показываем по кнопке, копируем без показа.
    document.querySelectorAll('[data-reveal-secret]').forEach((button) => {
        button.addEventListener('click', () => {
            const input = document.getElementById(button.dataset.revealSecret);
            if (!input) return;
            const hidden = input.type === 'password';
            input.type = hidden ? 'text' : 'password';
            button.textContent = hidden ? 'Скрыть' : 'Показать';
        });
    });
    document.querySelectorAll('[data-copy-secret]').forEach((button) => {
        button.addEventListener('click', async () => {
            const input = document.getElementById(button.dataset.copySecret);
            if (!input?.value) return;
            try {
                await navigator.clipboard.writeText(input.value);
                button.textContent = 'Скопировано';
                setTimeout(() => { button.textContent = 'Копировать'; }, 1500);
            } catch (error) {
                input.type = 'text';
                input.select();
            }
        });
    });

    const accessBlockDayInput = document.getElementById('access_block_day');
    if (accessBlockDayInput) {
        accessBlockDayInput.addEventListener('change', normalizeAccessBlockDay);
        accessBlockDayInput.addEventListener('blur', normalizeAccessBlockDay);
    }

    const hikvisionManualSyncBtn = document.getElementById('hikvisionManualSyncBtn');
    if (hikvisionManualSyncBtn) {
        hikvisionManualSyncBtn.addEventListener('click', requestHikvisionSync);
    }
    document.querySelectorAll('[data-open-hikvision-door]').forEach((button) => {
        button.addEventListener('click', () => requestHikvisionDoorOpen(button.dataset.openHikvisionDoor, button));
    });
    document.querySelectorAll('[data-clear-hikvision-device]').forEach((button) => {
        button.addEventListener('click', () => requestHikvisionClearDevice(button.dataset.clearHikvisionDevice, button));
    });

    const bridgeStatusRefreshBtn = document.getElementById('bridgeStatusRefreshBtn');
    if (bridgeStatusRefreshBtn) {
        bridgeStatusRefreshBtn.addEventListener('click', loadBridgeStatus);
    }
    document.addEventListener('visibilitychange', syncBridgePolling);
    document.addEventListener('settings:tab-change', syncBridgePolling);
    syncBridgePolling();
    const bridgePauseBtn = document.getElementById('bridgePauseBtn');
    if (bridgePauseBtn) bridgePauseBtn.addEventListener('click', () => requestBridgeControl(bridgePauseBtn.dataset.action || 'pause'));
    const bridgeStopBtn = document.getElementById('bridgeStopBtn');
    if (bridgeStopBtn) bridgeStopBtn.addEventListener('click', () => requestBridgeControl('stop'));

    const bridgeResultsBtn = document.getElementById('bridgeResultsBtn');
    if (bridgeResultsBtn) bridgeResultsBtn.addEventListener('click', openBridgeResultsModal);
    const copyBridgeLogsBtn = document.getElementById('copyBridgeLogsBtn');
    if (copyBridgeLogsBtn) copyBridgeLogsBtn.addEventListener('click', copyBridgeLiveLogs);
    ['bridgeResultsDeviceFilter', 'bridgeResultsTypeFilter', 'bridgeResultsSearch'].forEach(id => {
        const el = document.getElementById(id);
        if (el) el.addEventListener(id === 'bridgeResultsSearch' ? 'input' : 'change', renderBridgeResultsList);
    });

    initializeSettingsDirtyTracking();
}

function getAccessPolicyValue() {
    return document.getElementById('access_payment_policy')?.value || 'partial_current_month';
}

function normalizeAccessDebtMonths() {
    const input = document.getElementById('access_max_debt_months');
    if (!input) return 1;
    const value = parseInt(input.value || '1', 10);
    const normalized = Math.max(1, Math.min(36, Number.isFinite(value) ? value : 1));
    input.value = normalized;
    return normalized;
}

function updateAccessPaymentPolicyUI() {
    const policy = getAccessPolicyValue();
    const info = ACCESS_POLICY_INFO[policy] || ACCESS_POLICY_INFO.partial_current_month;
    const debtGroup = document.getElementById('accessDebtMonthsGroup');
    const help = document.getElementById('accessPaymentPolicyHelp');
    const infoCard = document.getElementById('accessPolicyDetails');
    const trigger = document.getElementById('accessPolicyTrigger');
    const menu = document.getElementById('accessPolicyMenu');
    const showDebtLimit = policy === 'any_payment_this_month';

    if (debtGroup) debtGroup.classList.toggle('is-hidden', !showDebtLimit);
    if (help) help.textContent = info.short;
    if (trigger) trigger.textContent = info.title;
    if (menu) {
        menu.querySelectorAll('.access-policy-option').forEach((option) => {
            const isActive = option.dataset.value === policy;
            option.classList.toggle('is-active', isActive);
            option.setAttribute('aria-selected', isActive ? 'true' : 'false');
        });
    }
    if (infoCard) {
        infoCard.innerHTML = `<strong>${info.short}</strong><br>${info.details}<span class="access-policy-example">${info.example}</span>`;
    }
    if (showDebtLimit) normalizeAccessDebtMonths();
}

function attachAccessPaymentPolicyControls() {
    const policySelect = document.getElementById('access_payment_policy');
    const infoButton = document.getElementById('accessPolicyInfoButton');
    const debtInput = document.getElementById('access_max_debt_months');
    const dropdown = document.getElementById('accessPolicyDropdown');
    const trigger = document.getElementById('accessPolicyTrigger');
    const menu = document.getElementById('accessPolicyMenu');

    if (menu && policySelect && !menu.dataset.ready) {
        menu.innerHTML = Object.entries(ACCESS_POLICY_INFO).map(([value, info]) => `
            <button type="button" class="access-policy-option" role="option" data-value="${value}">
                <span class="access-policy-option-title">${info.title}</span>
                <span class="access-policy-option-description">${info.short}</span>
            </button>
        `).join('');
        menu.dataset.ready = 'true';
    }

    if (policySelect) {
        policySelect.addEventListener('change', updateAccessPaymentPolicyUI);
    }
    if (trigger && dropdown) {
        trigger.addEventListener('click', () => {
            const isOpen = dropdown.classList.toggle('is-open');
            trigger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
        });
    }
    if (menu && policySelect && dropdown && trigger) {
        menu.addEventListener('click', (event) => {
            const option = event.target.closest('.access-policy-option');
            if (!option) return;
            policySelect.value = option.dataset.value || 'partial_current_month';
            policySelect.dispatchEvent(new Event('change', { bubbles: true }));
            dropdown.classList.remove('is-open');
            trigger.setAttribute('aria-expanded', 'false');
        });
    }
    if (debtInput) {
        debtInput.addEventListener('change', normalizeAccessDebtMonths);
        debtInput.addEventListener('blur', normalizeAccessDebtMonths);
    }
    if (infoButton) {
        infoButton.addEventListener('click', () => {
            const infoCard = document.getElementById('accessPolicyDetails');
            if (!infoCard) return;
            const isOpen = infoCard.classList.toggle('is-open');
            infoButton.classList.toggle('is-open', isOpen);
        });
    }
    document.addEventListener('click', (event) => {
        const infoCard = document.getElementById('accessPolicyDetails');
        if (!infoButton || !infoCard || !infoCard.classList.contains('is-open')) return;
        if (event.target.closest('.access-policy-label')) return;
        infoCard.classList.remove('is-open');
        infoButton.classList.remove('is-open');
    });
    document.addEventListener('click', (event) => {
        if (!dropdown || !trigger || !dropdown.classList.contains('is-open')) return;
        if (event.target.closest('#accessPolicyDropdown')) return;
        dropdown.classList.remove('is-open');
        trigger.setAttribute('aria-expanded', 'false');
    });
    updateAccessPaymentPolicyUI();
}

function normalizeAccessBlockDay() {
    const input = document.getElementById('access_block_day');
    if (!input) return 10;
    const value = parseInt(input.value || '10', 10);
    const normalized = Math.max(1, Math.min(31, Number.isFinite(value) ? value : 10));
    input.value = normalized;
    return normalized;
}

function attachTemplateTokenButtons() {
    document.querySelectorAll('.template-token-list').forEach(list => {
        list.addEventListener('click', (event) => {
            const button = event.target.closest('.template-token-btn');
            if (!button) return;

            const textarea = document.getElementById(list.dataset.templateTarget || '');
            const token = button.dataset.token || '';
            if (!textarea || !token) return;

            const start = textarea.selectionStart ?? textarea.value.length;
            const end = textarea.selectionEnd ?? textarea.value.length;
            textarea.value = `${textarea.value.slice(0, start)}${token}${textarea.value.slice(end)}`;

            const cursor = start + token.length;
            textarea.focus();
            textarea.setSelectionRange(cursor, cursor);
            textarea.dispatchEvent(new Event('input', { bubbles: true }));
        });
    });
}

function attachWorkingDayToggles() {
    const container = document.getElementById('working-days');
    if (!container) return;
    container.addEventListener('click', (e) => {
        const btn = e.target.closest('.day-toggle');
        if (!btn) return;
        btn.classList.toggle('active');
        btn.setAttribute('aria-pressed', btn.classList.contains('active') ? 'true' : 'false');
        updateSettingsFormDirtyState(document.getElementById('settingsForm'));
    });
}

function collectWorkingDays() {
    return Array.from(document.querySelectorAll('.day-toggle.active'))
        .map(btn => parseInt(btn.dataset.day, 10));
}

function setWorkingDays(days) {
    const set = new Set(days || []);
    document.querySelectorAll('.day-toggle').forEach(btn => {
        const day = parseInt(btn.dataset.day, 10);
        if (set.has(day)) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
        btn.setAttribute('aria-pressed', btn.classList.contains('active') ? 'true' : 'false');
    });
}

function getDefaultProviderCallback(providerId) {
    return `${window.location.origin}/api/payments/${providerId}/callback`;
}

function renderPaymentProviderConfigs() {
    const container = document.getElementById('paymentProviderConfigs');
    if (!container) return;

    container.innerHTML = PAYMENT_PROVIDER_DEFINITIONS.map((provider) => {
        const config = paymentProviderConfigs[provider.id] || {};
        const mode = config.mode === 'production' ? 'production' : 'sandbox';
        const fieldsHtml = (provider.fields || []).map((field) => {
            const fieldValue = field.key === 'callback_url'
                ? (config[field.key] || getDefaultProviderCallback(provider.id))
                : (config[field.key] || '');
            const type = field.type || 'text';
            const wideClass = field.wide ? ' is-wide' : '';
            return `
                <div class="payment-provider-field${wideClass}">
                    <label for="payment_${provider.id}_${field.key}">${escapeHtml(field.label)}</label>
                    <input
                        type="${type}"
                        id="payment_${provider.id}_${field.key}"
                        class="form-input-modern"
                        data-payment-provider="${provider.id}"
                        data-payment-field="${field.key}"
                        value="${escapeHtml(fieldValue)}"
                        placeholder="${escapeHtml(field.placeholder || '')}">
                </div>
            `;
        }).join('');

        const docsLink = provider.docsUrl
            ? `<a href="${escapeHtml(provider.docsUrl)}" target="_blank" rel="noopener" class="payment-provider-doc">Документация</a>`
            : '<span class="payment-provider-doc">Документации нет</span>';

        return `
            <div class="payment-provider-card ${config.enabled ? 'is-enabled' : ''}" data-provider-card="${provider.id}">
                <div class="payment-provider-card-header">
                    <div>
                        <div class="payment-provider-title">
                            <img src="${escapeHtml(provider.logo)}" alt="${escapeHtml(provider.title)}" class="payment-provider-logo">
                            <span>${escapeHtml(provider.title)}</span>
                        </div>
                        <p class="payment-provider-note">${escapeHtml(provider.note)}</p>
                    </div>
                    <label class="switch-toggle" title="Включить API-интеграцию">
                        <input type="checkbox" data-payment-provider="${provider.id}" data-payment-field="enabled" ${config.enabled ? 'checked' : ''}>
                        <span class="switch-slider"></span>
                    </label>
                </div>
                <div class="payment-provider-fields" data-payment-provider-details>
                    <div class="payment-provider-field">
                        <span>Режим</span>
                        <select class="form-input-modern" data-payment-provider="${provider.id}" data-payment-field="mode">
                            <option value="sandbox" ${mode === 'sandbox' ? 'selected' : ''}>Sandbox</option>
                            <option value="production" ${mode === 'production' ? 'selected' : ''}>Production</option>
                        </select>
                    </div>
                    ${fieldsHtml}
                </div>
                <div class="payment-provider-example" data-payment-provider-details>${escapeHtml(provider.example)} ${docsLink}</div>
            </div>
        `;
    }).join('');

    container.querySelectorAll('input, select').forEach((element) => {
        element.addEventListener('input', () => updateSettingsFormDirtyState(document.getElementById('integrationsForm')));
        element.addEventListener('change', () => {
            if (element.dataset.paymentField === 'enabled') {
                const card = element.closest('[data-provider-card]');
                if (card) card.classList.toggle('is-enabled', element.checked);
            }
            updateSettingsFormDirtyState(document.getElementById('integrationsForm'));
        });
    });
    if (window.lucide) window.lucide.createIcons();
}

function collectPaymentProviderConfigs() {
    const configs = {};
    document.querySelectorAll('[data-provider-card]').forEach((card) => {
        const providerId = card.dataset.providerCard;
        const config = {};
        card.querySelectorAll('[data-payment-field]').forEach((element) => {
            const field = element.dataset.paymentField;
            if (!field) return;
            if (element.type === 'checkbox') {
                config[field] = element.checked;
            } else {
                config[field] = (element.value || '').trim();
            }
        });
        configs[providerId] = config;
    });
    return configs;
}

async function loadSettings() {
    try {
        const resp = await fetch('/api/club-settings');
        const data = await resp.json();
        document.getElementById('system_name').value = data.system_name || '';
        setSystemLogoPreview(data.logo_url, data.logo_is_custom);
        setSystemSquareLogoPreview(data.square_logo_url, data.square_logo_is_custom);
        setWorkingDays(data.working_days || []);
        document.getElementById('work_start_time').value = data.work_start_time || '09:00';
        document.getElementById('work_end_time').value = data.work_end_time || '21:00';
        document.getElementById('max_groups_per_slot').value = data.max_groups_per_slot || 1;
        document.getElementById('block_future_payments').checked = !!data.block_future_payments;
        const accessBlockDayEl = document.getElementById('access_block_day');
        const accessPaymentPolicyEl = document.getElementById('access_payment_policy');
        const hikvisionDailySyncTimeEl = document.getElementById('hikvision_daily_sync_time');
        const hikvisionParallelDevicesEl = document.getElementById('hikvision_parallel_devices');
        const hikvisionCleanupStaleUsersEl = document.getElementById('hikvision_cleanup_stale_users');
        const accessDebtStartMonthEl = document.getElementById('access_debt_start_month');
        const accessDebtStartYearEl = document.getElementById('access_debt_start_year');
        const minLessonsEl = document.getElementById('min_lessons_for_debt');
        if (minLessonsEl) minLessonsEl.value = data.min_lessons_for_debt ?? 4;
        const autoArchiveEl = document.getElementById('auto_archive_after_months');
        if (autoArchiveEl) {
            autoArchiveEl.value = data.auto_archive_after_months ?? 0;
            refreshAutoArchivePreview();
        }
        const accessMaxDebtMonthsEl = document.getElementById('access_max_debt_months');
        const hikvisionDeviceKeyEl = document.getElementById('hikvision_device_key');
        if (accessBlockDayEl) {
            accessBlockDayEl.value = data.access_block_day || 10;
            normalizeAccessBlockDay();
        }
        if (accessPaymentPolicyEl) accessPaymentPolicyEl.value = data.access_payment_policy || 'partial_current_month';
        if (hikvisionDailySyncTimeEl) hikvisionDailySyncTimeEl.value = data.hikvision_daily_sync_time || '03:00';
        if (hikvisionParallelDevicesEl) hikvisionParallelDevicesEl.checked = !!data.hikvision_parallel_devices;
        if (hikvisionCleanupStaleUsersEl) hikvisionCleanupStaleUsersEl.checked = data.hikvision_cleanup_stale_users !== false;
        if (accessDebtStartMonthEl) accessDebtStartMonthEl.value = data.access_debt_start_month || '';
        if (accessDebtStartYearEl) accessDebtStartYearEl.value = data.access_debt_start_year || '';
        if (accessMaxDebtMonthsEl) {
            const loadedDebtMonths = parseInt(data.access_max_debt_months || '1', 10);
            accessMaxDebtMonthsEl.value = Math.max(1, Number.isFinite(loadedDebtMonths) ? loadedDebtMonths : 1);
        }
        if (hikvisionDeviceKeyEl) hikvisionDeviceKeyEl.value = data.hikvision_device_key || '';
        setHikvisionDevices(data.hikvision_devices || []);
        const cameraSettingDefaults = {
            camera_kiosk_url: '',
            camera_stream_fps: 30,
            camera_tracking_fps: 30,
            camera_detection_fps: 10,
            camera_width: 1920,
            camera_height: 1080,
            camera_recognition_frames: 3,
            camera_result_hold_seconds: 10,
            camera_kiosk_port: 8090,
        };
        Object.entries(cameraSettingDefaults).forEach(([id, fallback]) => {
            const element = document.getElementById(id);
            if (element) element.value = data[id] ?? fallback;
        });
        const cameraKioskEnabledEl = document.getElementById('camera_kiosk_enabled');
        if (cameraKioskEnabledEl) cameraKioskEnabledEl.checked = !!data.camera_kiosk_enabled;
        document.getElementById('rewards_reset_period_months').value = data.rewards_reset_period_months || 1;
        // Убедимся, что значение кратно 5 и в диапазоне 5-50
        const podiumValue = data.podium_display_count || 20;
        const normalizedPodiumValue = Math.max(5, Math.min(50, Math.round(podiumValue / 5) * 5));
        document.getElementById('podium_display_count').value = normalizedPodiumValue;

        // Загружаем настройки Telegram (если элементы существуют)
        const telegramTokenEl = document.getElementById('telegram_bot_token');
        const telegramBotUrlEl = document.getElementById('telegram_bot_url');
        const telegramNotificationEl = document.getElementById('telegram_notification_template');
        const telegramRewardEl = document.getElementById('telegram_reward_template');
        const telegramCardEl = document.getElementById('telegram_card_template');
        const telegramPaymentEl = document.getElementById('telegram_payment_template');

        if (telegramTokenEl) telegramTokenEl.value = data.telegram_bot_token || '';
        if (telegramBotUrlEl) telegramBotUrlEl.value = data.telegram_bot_url || '';
        if (telegramNotificationEl) telegramNotificationEl.value = data.telegram_notification_template || '';
        if (telegramRewardEl) telegramRewardEl.value = data.telegram_reward_template || '';
        if (telegramCardEl) telegramCardEl.value = data.telegram_card_template || '';
        if (telegramPaymentEl) telegramPaymentEl.value = data.telegram_payment_template || '';

        // Телефоны руководства
        const directorPhoneEl = document.getElementById('director_phone');
        const founderPhoneEl = document.getElementById('founder_phone');
        const cashierPhoneEl = document.getElementById('cashier_phone');

        if (directorPhoneEl) directorPhoneEl.value = data.director_phone || '';
        if (founderPhoneEl) founderPhoneEl.value = data.founder_phone || '';
        if (cashierPhoneEl) cashierPhoneEl.value = data.cashier_phone || '';

        // Настройки камеры
        const rtspUrlEl = document.getElementById('rtsp_url_setting');
        if (rtspUrlEl) {
            rtspUrlEl.value = data.rtsp_url || '';
        }

        const clickEnabledEl = document.getElementById('payment_click_enabled');
        const clickQrEl = document.getElementById('payment_click_qr_url');
        const paymeEnabledEl = document.getElementById('payment_payme_enabled');
        const paymeQrEl = document.getElementById('payment_payme_qr_url');
        const uzumEnabledEl = document.getElementById('payment_uzum_enabled');
        const uzumQrEl = document.getElementById('payment_uzum_qr_url');
        const uzcardEnabledEl = document.getElementById('payment_uzcard_enabled');
        const humoEnabledEl = document.getElementById('payment_humo_enabled');
        const paynetEnabledEl = document.getElementById('payment_paynet_enabled');
        const paynetQrEl = document.getElementById('payment_paynet_qr_url');
        const multicardEnabledEl = document.getElementById('payment_multicard_enabled');
        const multicardQrEl = document.getElementById('payment_multicard_qr_url');
        const osonEnabledEl = document.getElementById('payment_oson_enabled');
        const osonQrEl = document.getElementById('payment_oson_qr_url');
        const transferEnabledEl = document.getElementById('payment_transfer_enabled');

        if (clickEnabledEl) clickEnabledEl.checked = !!data.payment_click_enabled;
        if (clickQrEl) clickQrEl.value = data.payment_click_qr_url || '';
        if (paymeEnabledEl) paymeEnabledEl.checked = !!data.payment_payme_enabled;
        if (paymeQrEl) paymeQrEl.value = data.payment_payme_qr_url || '';
        if (uzumEnabledEl) uzumEnabledEl.checked = !!data.payment_uzum_enabled;
        if (uzumQrEl) uzumQrEl.value = data.payment_uzum_qr_url || '';
        if (uzcardEnabledEl) uzcardEnabledEl.checked = !!data.payment_uzcard_enabled;
        if (humoEnabledEl) humoEnabledEl.checked = !!data.payment_humo_enabled;
        if (paynetEnabledEl) paynetEnabledEl.checked = !!data.payment_paynet_enabled;
        if (paynetQrEl) paynetQrEl.value = data.payment_paynet_qr_url || '';
        if (multicardEnabledEl) multicardEnabledEl.checked = !!data.payment_multicard_enabled;
        if (multicardQrEl) multicardQrEl.value = data.payment_multicard_qr_url || '';
        if (osonEnabledEl) osonEnabledEl.checked = !!data.payment_oson_enabled;
        if (osonQrEl) osonQrEl.value = data.payment_oson_qr_url || '';
        if (transferEnabledEl) transferEnabledEl.checked = !!data.payment_transfer_enabled;
        paymentProviderConfigs = data.payment_provider_configs && typeof data.payment_provider_configs === 'object'
            ? data.payment_provider_configs
            : {};
        renderPaymentProviderConfigs();

        // Статьи расхода
        expenseCategories = Array.isArray(data.expense_categories) ? data.expense_categories : [];
        if (!expenseCategories.length) {
            expenseCategories = ['Аренда', 'Зарплата', 'Оборудование', 'Коммунальные', 'Ремонт стадиона', 'Дивидент', 'Прочее'];
        }
        renderExpenseCategories();
    } catch (error) {
        console.error('Ошибка загрузки настроек:', error);
        alert('Не удалось загрузить настройки');
    }
}

function setHikvisionDevices(devices) {
    const list = Array.isArray(devices) ? devices : [];
    const entry = list.find((d) => d.name === 'entry') || list[0] || {};
    const exit = list.find((d) => d.name === 'exit') || list[1] || {};
    const protocol = entry.protocol || exit.protocol || 'https';
    const port = entry.port || exit.port || (protocol === 'http' ? 80 : 443);

    const entryIpEl = document.getElementById('hikvision_entry_ip');
    const exitIpEl = document.getElementById('hikvision_exit_ip');
    const protocolEl = document.getElementById('hikvision_protocol');
    const portEl = document.getElementById('hikvision_port');

    if (entryIpEl) entryIpEl.value = entry.ip || '192.168.68.107';
    if (exitIpEl) exitIpEl.value = exit.ip || '192.168.68.104';
    if (protocolEl) protocolEl.value = protocol;
    if (portEl) portEl.value = port;
}

function collectHikvisionDevices() {
    const protocol = document.getElementById('hikvision_protocol')?.value || 'https';
    const port = parseInt(document.getElementById('hikvision_port')?.value || (protocol === 'http' ? '80' : '443'), 10);
    const entryIp = (document.getElementById('hikvision_entry_ip')?.value || '').trim();
    const exitIp = (document.getElementById('hikvision_exit_ip')?.value || '').trim();

    return [
        { name: 'entry', ip: entryIp, protocol, port, doorNo: 1 },
        { name: 'exit', ip: exitIp, protocol, port, doorNo: 1 }
    ].filter((device) => device.ip);
}

function parseIntOr(raw, fallback) {
    const value = parseInt(String(raw ?? '').trim(), 10);
    return Number.isFinite(value) ? value : fallback;
}

// Какие поля сохраняет каждая форма: вкладка не трогает настройки других вкладок.
const SETTINGS_FORM_KEYS = {
    settingsForm: ['system_name', 'working_days', 'work_start_time', 'work_end_time', 'max_groups_per_slot'],
    paymentsForm: (key) => key === 'block_future_payments' || key === 'expense_categories'
        || (key.startsWith('payment_') && key !== 'payment_provider_configs'),
    accessForm: ['access_block_day', 'access_payment_policy', 'access_debt_start_month', 'access_debt_start_year',
        'access_max_debt_months', 'min_lessons_for_debt', 'auto_archive_after_months'],
    rewardsSettingsForm: ['rewards_reset_period_months', 'podium_display_count'],
    telegramSettingsForm: (key) => key.startsWith('telegram_') || key.endsWith('_phone'),
    hikvisionSettingsForm: (key) => key.startsWith('hikvision_'),
    cameraSettingsForm: (key) => key === 'rtsp_url' || key.startsWith('camera_'),
    integrationsForm: ['payment_provider_configs'],
};

function pickFormSettings(formId, data) {
    const rule = SETTINGS_FORM_KEYS[formId];
    const keep = Array.isArray(rule) ? (key) => rule.includes(key) : rule;
    return Object.fromEntries(Object.entries(data).filter(([key]) => keep(key)));
}

function setFormSaveState(form, text, kind = '') {
    const state = form.querySelector('[data-save-state]');
    if (!state) return;
    state.textContent = text;
    state.dataset.kind = kind;
}

async function saveSettingsForm(form) {
    const payload = pickFormSettings(form.id, gatherAllSettings());
    if ('system_name' in payload && !payload.system_name) {
        setFormSaveState(form, 'Введите название системы', 'error');
        document.getElementById('system_name')?.focus();
        return;
    }
    const buttons = getSettingsSubmitButtons(form);
    buttons.forEach((button) => { button.disabled = true; });
    setFormSaveState(form, 'Сохраняем…');
    try {
        const resp = await fetch('/api/club-settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await resp.json().catch(() => ({}));
        if (!resp.ok || !result.success) {
            updateSettingsFormDirtyState(form);
            setFormSaveState(form, result.message || 'Не удалось сохранить', 'error');
            return;
        }
        markSettingsFormClean(form);
        setFormSaveState(form, result.sync_queued ? 'Сохранено · терминалы обновятся' : 'Сохранено', 'ok');
    } catch (error) {
        console.error('Ошибка сохранения настроек:', error);
        updateSettingsFormDirtyState(form);
        setFormSaveState(form, 'Нет связи с сервером — попробуйте ещё раз', 'error');
    }
}

function syncBridgePolling() {
    const tabOpen = document.getElementById('hikvision-tab')?.classList.contains('active');
    const shouldPoll = tabOpen && document.visibilityState === 'visible'
        && Boolean(document.getElementById('bridgeStatusBanner'));
    if (shouldPoll && !bridgeStatusTimer) {
        loadBridgeStatus();
        bridgeStatusTimer = setInterval(loadBridgeStatus, 5000);
    } else if (!shouldPoll && bridgeStatusTimer) {
        clearInterval(bridgeStatusTimer);
        bridgeStatusTimer = null;
    }
}

async function requestHikvisionSync() {
    const btn = document.getElementById('hikvisionManualSyncBtn');
    if (btn) {
        btn.disabled = true;
        btn.classList.add('is-loading');
    }
    try {
        const resp = await fetch('/api/hikvision/sync', { method: 'POST' });
        const result = await resp.json();
        if (result.success) {
            alert('Команда синхронизации отправлена bridge');
            setTimeout(() => {
                loadSyncHistory();
            }, 500);
        } else {
            alert('Ошибка: ' + (result.message || 'не удалось отправить команду'));
        }
    } catch (error) {
        console.error('Ошибка запуска синхронизации Hikvision:', error);
        alert('Не удалось отправить команду синхронизации');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.classList.remove('is-loading');
        }
    }
}

async function requestHikvisionDoorOpen(deviceName, btn) {
    const label = deviceName === 'entry' ? 'вход' : 'выход';
    if (!confirm(`Открыть турникет "${label}" сейчас?`)) return;

    if (btn) {
        btn.disabled = true;
        btn.classList.add('is-loading');
    }
    try {
        const resp = await fetch('/api/hikvision/open-door', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_name: deviceName })
        });
        const result = await resp.json();
        if (result.success) {
            alert(result.message || `Команда открыть ${label} отправлена bridge`);
            setTimeout(loadSyncHistory, 500);
        } else {
            alert('Ошибка: ' + (result.message || 'не удалось открыть турникет'));
        }
    } catch (error) {
        console.error('Ошибка открытия турникета Hikvision:', error);
        alert('Не удалось отправить команду открытия турникета');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.classList.remove('is-loading');
        }
    }
}

async function requestHikvisionClearDevice(deviceName, btn) {
    const label = deviceName === 'entry' ? 'вход' : 'выход';
    const typed = prompt(`Это удалит ВСЕХ людей из памяти терминала "${label}". Напишите ОЧИСТИТЬ для подтверждения.`);
    if (typed !== 'ОЧИСТИТЬ') return;

    if (btn) {
        btn.disabled = true;
        btn.classList.add('is-loading');
    }
    try {
        const resp = await fetch('/api/hikvision/clear-device', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ device_name: deviceName })
        });
        const result = await resp.json();
        if (result.success) {
            alert(result.message || `Команда очистить ${label} отправлена bridge`);
            setTimeout(loadSyncHistory, 500);
            setTimeout(loadBridgeStatus, 500);
        } else {
            alert('Ошибка: ' + (result.message || 'не удалось отправить очистку терминала'));
        }
    } catch (error) {
        console.error('Ошибка очистки терминала Hikvision:', error);
        alert('Не удалось отправить команду очистки терминала');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.classList.remove('is-loading');
        }
    }
}

async function requestBridgeControl(action) {
    const labels = {
        pause: 'поставить запись на паузу',
        resume: 'продолжить запись',
        stop: 'полностью остановить текущую запись',
        restart: 'перезапустить bridge (связь пропадет на несколько секунд)',
        update: 'скачать свежий код с GitHub и перезапустить bridge'
    };
    if (!confirm(`Вы уверены, что хотите ${labels[action] || 'управлять bridge'}?`)) return;

    try {
        const resp = await fetch('/api/hikvision/bridge/control', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ action })
        });
        const result = await resp.json();
        if (result.success) {
            alert(result.message || 'Команда отправлена bridge');
            setTimeout(loadBridgeStatus, 500);
            if (action === 'restart' || action === 'update') {
                // Процесс поднимается заново секунд за 10-15.
                [5000, 12000, 20000].forEach(delay => setTimeout(loadBridgeStatus, delay));
            }
        } else {
            alert('Ошибка: ' + (result.message || 'не удалось отправить команду'));
        }
    } catch (error) {
        console.error('Ошибка управления bridge:', error);
        alert('Не удалось отправить команду bridge');
    }
}

function cacheBustUrl(url) {
    if (!url) return '';
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}v=${Date.now()}`;
}

function updateVisibleBrandLogos(url) {
    if (!url) return;
    document.querySelectorAll('.sidebar-logo-icon, .login-logo, .portal-brand-logo').forEach(img => {
        img.src = cacheBustUrl(url);
    });
}

function setSystemLogoPreview(url, isCustom) {
    const preview = document.getElementById('system_logo_preview');
    if (preview && url) preview.src = cacheBustUrl(url);

    const status = document.getElementById('logo_status_text');
    if (status) {
        status.textContent = isCustom ? 'Горизонтальный · загружен' : 'Горизонтальный · системный';
    }

    const fileName = document.getElementById('logo_file_name');
    if (fileName && !isCustom) fileName.textContent = '';
    // Сбрасывать есть что, только пока загружен свой логотип.
    const reset = document.getElementById('resetLogoBtn');
    if (reset) { reset.disabled = !isCustom; reset.hidden = !isCustom; }

    updateVisibleBrandLogos(url);
}

function setSystemSquareLogoPreview(url, isCustom) {
    const preview = document.getElementById('system_square_logo_preview');
    if (preview && url) preview.src = cacheBustUrl(url);

    const status = document.getElementById('square_logo_status_text');
    if (status) status.textContent = isCustom ? 'Квадратный · загружен' : 'Квадратный · системный';

    const fileName = document.getElementById('square_logo_file_name');
    if (fileName && !isCustom) fileName.textContent = '';
    const reset = document.getElementById('resetSquareLogoBtn');
    if (reset) { reset.disabled = !isCustom; reset.hidden = !isCustom; }
}

async function uploadSystemLogo() {
    const fileInput = document.getElementById('system_logo_file');
    const button = document.getElementById('uploadLogoBtn');
    const file = fileInput?.files?.[0];
    if (!file) {
        fileInput?.click();
        return;
    }

    const formData = new FormData();
    formData.append('logo', file);
    if (button) button.disabled = true;
    const status = document.getElementById('logo_status_text');
    if (status) status.textContent = 'Загрузка...';

    try {
        const resp = await fetch('/api/club-settings/logo', {
            method: 'POST',
            body: formData
        });
        const result = await resp.json();
        if (!result.success) {
            alert('Ошибка: ' + (result.message || 'Не удалось загрузить логотип'));
            return;
        }
        setSystemLogoPreview(result.logo_url, result.logo_is_custom);
        fileInput.value = '';
        const fileName = document.getElementById('logo_file_name');
        if (fileName) fileName.textContent = file.name;
    } catch (error) {
        console.error('Ошибка загрузки логотипа:', error);
        alert('Не удалось загрузить логотип');
    } finally {
        if (button) button.disabled = false;
    }
}

async function uploadSystemSquareLogo() {
    const fileInput = document.getElementById('system_square_logo_file');
    const button = document.getElementById('uploadSquareLogoBtn');
    const file = fileInput?.files?.[0];
    if (!file) {
        fileInput?.click();
        return;
    }

    const formData = new FormData();
    formData.append('logo', file);
    if (button) button.disabled = true;
    const status = document.getElementById('square_logo_status_text');
    if (status) status.textContent = 'Загрузка...';

    try {
        const resp = await fetch('/api/club-settings/square-logo', {
            method: 'POST',
            body: formData
        });
        const result = await resp.json();
        if (!result.success) {
            alert('Ошибка: ' + (result.message || 'Не удалось загрузить квадратный логотип'));
            return;
        }
        setSystemSquareLogoPreview(result.square_logo_url, result.square_logo_is_custom);
        fileInput.value = '';
        const fileName = document.getElementById('square_logo_file_name');
        if (fileName) fileName.textContent = file.name;
    } catch (error) {
        console.error('Ошибка загрузки квадратного логотипа:', error);
        alert('Не удалось загрузить квадратный логотип');
    } finally {
        if (button) button.disabled = false;
    }
}

async function resetSystemLogo() {
    if (!confirm('Сбросить логотип на системный?')) return;
    const button = document.getElementById('resetLogoBtn');
    if (button) button.disabled = true;

    try {
        const resp = await fetch('/api/club-settings/logo', { method: 'DELETE' });
        const result = await resp.json();
        if (!result.success) {
            alert('Ошибка: ' + (result.message || 'Не удалось сбросить логотип'));
            return;
        }
        setSystemLogoPreview(result.logo_url, result.logo_is_custom);
        const fileInput = document.getElementById('system_logo_file');
        if (fileInput) fileInput.value = '';
    } catch (error) {
        console.error('Ошибка сброса логотипа:', error);
        alert('Не удалось сбросить логотип');
        if (button) button.disabled = false;
    }
}

async function resetSystemSquareLogo() {
    if (!confirm('Сбросить квадратный логотип на системный?')) return;
    const button = document.getElementById('resetSquareLogoBtn');
    if (button) button.disabled = true;

    try {
        const resp = await fetch('/api/club-settings/square-logo', { method: 'DELETE' });
        const result = await resp.json();
        if (!result.success) {
            alert('Ошибка: ' + (result.message || 'Не удалось сбросить квадратный логотип'));
            return;
        }
        setSystemSquareLogoPreview(result.square_logo_url, result.square_logo_is_custom);
        const fileInput = document.getElementById('system_square_logo_file');
        if (fileInput) fileInput.value = '';
    } catch (error) {
        console.error('Ошибка сброса квадратного логотипа:', error);
        alert('Не удалось сбросить квадратный логотип');
        if (button) button.disabled = false;
    }
}

function gatherAllSettings() {
    const accessPaymentPolicy = document.getElementById('access_payment_policy')?.value || 'partial_current_month';
    const accessMaxDebtMonths = accessPaymentPolicy === 'any_payment_this_month'
        ? normalizeAccessDebtMonths()
        : 0;
    return {
        system_name: document.getElementById('system_name').value.trim(),
        working_days: collectWorkingDays(),
        work_start_time: document.getElementById('work_start_time').value,
        work_end_time: document.getElementById('work_end_time').value,
        max_groups_per_slot: parseIntOr(document.getElementById('max_groups_per_slot').value, 1),
        block_future_payments: document.getElementById('block_future_payments').checked,
        access_block_day: normalizeAccessBlockDay(),
        access_payment_policy: accessPaymentPolicy,
        hikvision_daily_sync_time: document.getElementById('hikvision_daily_sync_time')?.value || '03:00',
        hikvision_parallel_devices: document.getElementById('hikvision_parallel_devices')?.checked || false,
        hikvision_cleanup_stale_users: document.getElementById('hikvision_cleanup_stale_users')?.checked !== false,
        access_debt_start_month: document.getElementById('access_debt_start_month')?.value || null,
        access_debt_start_year: document.getElementById('access_debt_start_year')?.value || null,
        access_max_debt_months: accessMaxDebtMonths,
        min_lessons_for_debt: parseIntOr(document.getElementById('min_lessons_for_debt')?.value, 4),
        auto_archive_after_months: parseIntOr(document.getElementById('auto_archive_after_months')?.value, 0),
        hikvision_device_key: (document.getElementById('hikvision_device_key')?.value || '').trim(),
        hikvision_devices: collectHikvisionDevices(),
        rewards_reset_period_months: parseInt(document.getElementById('rewards_reset_period_months').value, 10),
        podium_display_count: parseInt(document.getElementById('podium_display_count').value, 10),
        telegram_bot_url: (document.getElementById('telegram_bot_url')?.value || '').trim(),
        telegram_bot_token: (document.getElementById('telegram_bot_token')?.value || '').trim(),
        telegram_notification_template: (document.getElementById('telegram_notification_template')?.value || '').trim(),
        telegram_reward_template: (document.getElementById('telegram_reward_template')?.value || '').trim(),
        telegram_card_template: (document.getElementById('telegram_card_template')?.value || '').trim(),
        telegram_payment_template: (document.getElementById('telegram_payment_template')?.value || '').trim(),
        director_phone: (document.getElementById('director_phone')?.value || '').trim(),
        founder_phone: (document.getElementById('founder_phone')?.value || '').trim(),
        cashier_phone: (document.getElementById('cashier_phone')?.value || '').trim(),
        rtsp_url: (document.getElementById('rtsp_url_setting')?.value || '').trim(),
        camera_kiosk_enabled: document.getElementById('camera_kiosk_enabled')?.checked || false,
        camera_kiosk_url: (document.getElementById('camera_kiosk_url')?.value || '').trim(),
        camera_stream_fps: parseInt(document.getElementById('camera_stream_fps')?.value || '30', 10),
        camera_tracking_fps: parseInt(document.getElementById('camera_tracking_fps')?.value || '30', 10),
        camera_detection_fps: parseInt(document.getElementById('camera_detection_fps')?.value || '10', 10),
        camera_width: parseInt(document.getElementById('camera_width')?.value || '1920', 10),
        camera_height: parseInt(document.getElementById('camera_height')?.value || '1080', 10),
        camera_recognition_frames: parseInt(document.getElementById('camera_recognition_frames')?.value || '3', 10),
        camera_result_hold_seconds: parseInt(document.getElementById('camera_result_hold_seconds')?.value || '10', 10),
        camera_kiosk_port: parseInt(document.getElementById('camera_kiosk_port')?.value || '8090', 10),
        payment_click_enabled: document.getElementById('payment_click_enabled')?.checked || false,
        payment_click_qr_url: (document.getElementById('payment_click_qr_url')?.value || '').trim(),
        payment_payme_enabled: document.getElementById('payment_payme_enabled')?.checked || false,
        payment_payme_qr_url: (document.getElementById('payment_payme_qr_url')?.value || '').trim(),
        payment_uzum_enabled: document.getElementById('payment_uzum_enabled')?.checked || false,
        payment_uzum_qr_url: (document.getElementById('payment_uzum_qr_url')?.value || '').trim(),
        payment_uzcard_enabled: document.getElementById('payment_uzcard_enabled')?.checked || false,
        payment_humo_enabled: document.getElementById('payment_humo_enabled')?.checked || false,
        payment_paynet_enabled: document.getElementById('payment_paynet_enabled')?.checked || false,
        payment_paynet_qr_url: (document.getElementById('payment_paynet_qr_url')?.value || '').trim(),
        payment_multicard_enabled: document.getElementById('payment_multicard_enabled')?.checked || false,
        payment_multicard_qr_url: (document.getElementById('payment_multicard_qr_url')?.value || '').trim(),
        payment_oson_enabled: document.getElementById('payment_oson_enabled')?.checked || false,
        payment_oson_qr_url: (document.getElementById('payment_oson_qr_url')?.value || '').trim(),
        payment_transfer_enabled: document.getElementById('payment_transfer_enabled')?.checked || false,
        payment_provider_configs: collectPaymentProviderConfigs(),
        expense_categories: expenseCategories
    };
}

function renderExpenseCategories() {
    const list = document.getElementById('expense-categories-list');
    if (!list) return;

    list.innerHTML = '';

    if (!expenseCategories.length) {
        const empty = document.createElement('div');
        empty.textContent = 'Статей расхода пока нет';
        empty.style.color = '#94a3b8';
        empty.style.fontSize = '14px';
        list.appendChild(empty);
        return;
    }

    expenseCategories.forEach((category, index) => {
        const item = document.createElement('div');
        item.className = 'expense-category-chip';

        const name = document.createElement('span');
        name.textContent = category;

        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'expense-category-remove';
        removeBtn.textContent = '×';
        removeBtn.title = 'Удалить статью';
        removeBtn.addEventListener('click', () => removeExpenseCategorySetting(index));

        item.appendChild(name);
        item.appendChild(removeBtn);
        list.appendChild(item);
    });
}

function serializeSettingsForm(form) {
    const values = [];
    form.querySelectorAll('input, select, textarea').forEach((el) => {
        if (el.dataset.ignoreDirty === 'true') return;
        const key = el.name || el.id;
        if (!key) return;
        if (el.type === 'file') {
            const files = Array.from(el.files || []).map((file) => `${file.name}:${file.size}`).join(',');
            values.push(`${key}=file:${files}`);
        } else if (el.type === 'checkbox' || el.type === 'radio') {
            values.push(`${key}=${el.checked ? '1' : '0'}`);
        } else {
            values.push(`${key}=${el.value}`);
        }
    });
    if (form.querySelector('#working-days')) {
        values.push(`working_days=${collectWorkingDays().join(',')}`);
    }
    if (form.querySelector('#expense-categories-list')) {
        values.push(`expenseCategories=${JSON.stringify(expenseCategories)}`);
    }
    return values.join('|');
}

function getSettingsSubmitButtons(form) {
    const buttons = Array.from(form.querySelectorAll('button[type="submit"], input[type="submit"]'));
    if (form.id) {
        buttons.push(...Array.from(document.querySelectorAll(`button[form="${form.id}"], input[form="${form.id}"]`)));
    }
    return buttons;
}

function updateSettingsFormDirtyState(form) {
    if (!settingsDirtyTrackingReady || !form) return;
    const initial = settingsFormSnapshots.get(form.id || form);
    const dirty = serializeSettingsForm(form) !== initial;
    getSettingsSubmitButtons(form).forEach((button) => {
        button.disabled = !dirty;
        button.title = dirty ? '' : 'Нет изменений для сохранения';
    });
    form.classList.toggle('is-dirty', dirty);
    if (dirty) setFormSaveState(form, 'Есть несохранённые изменения', 'dirty');
    else if (form.querySelector('[data-save-state]')?.dataset.kind === 'dirty') setFormSaveState(form, '');
}

function markSettingsFormClean(form) {
    settingsFormSnapshots.set(form.id || form, serializeSettingsForm(form));
    updateSettingsFormDirtyState(form);
}

function initializeSettingsDirtyTracking() {
    const forms = Array.from(document.querySelectorAll('.settings-form'));
    settingsDirtyTrackingReady = true;
    forms.forEach((form) => {
        settingsFormSnapshots.set(form.id || form, serializeSettingsForm(form));
        form.addEventListener('input', () => updateSettingsFormDirtyState(form));
        form.addEventListener('change', () => updateSettingsFormDirtyState(form));
        updateSettingsFormDirtyState(form);
    });
}

function addExpenseCategorySetting() {
    const input = document.getElementById('expense-category-input');
    if (!input) return;

    const value = (input.value || '').trim();
    if (!value) return;

    const exists = expenseCategories.some((cat) => cat.toLowerCase() === value.toLowerCase());
    if (exists) {
        alert('Такая статья уже есть');
        return;
    }

    expenseCategories.push(value);
    input.value = '';
    renderExpenseCategories();
    updateSettingsFormDirtyState(document.getElementById('paymentsForm'));
}

function removeExpenseCategorySetting(index) {
    if (index < 0 || index >= expenseCategories.length) return;
    expenseCategories.splice(index, 1);
    renderExpenseCategories();
    updateSettingsFormDirtyState(document.getElementById('paymentsForm'));
}

window.addExpenseCategorySetting = addExpenseCategorySetting;
window.removeExpenseCategorySetting = removeExpenseCategorySetting;

// --- ИСТОРИЯ СИНХРОНИЗАЦИЙ HIKVISION ---

async function loadSyncHistory() {
    const body = document.getElementById('hikvisionSyncHistoryBody');
    if (!body) return;

    try {
        const resp = await fetch('/api/hikvision/commands/history');
        if (!resp.ok) throw new Error('Ошибка сети при загрузке истории');
        const data = await resp.json();
        
        if (!data.success) {
            body.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #ef4444;">${data.message || 'Ошибка загрузки'}</td></tr>`;
            return;
        }

        const commands = data.commands || [];
        if (commands.length === 0) {
            body.innerHTML = '<tr><td colspan="5" style="text-align: center; color: var(--theme-text-secondary); padding: 20px;">История синхронизаций пуста</td></tr>';
            return;
        }

        body.innerHTML = '';
        commands.forEach(cmd => {
            const tr = document.createElement('tr');

            // 1. Дата запуска
            const tdDate = document.createElement('td');
            tdDate.textContent = formatDateTime(cmd.created_at);
            tr.appendChild(tdDate);

            // 2. Причина запуска
            const tdReason = document.createElement('td');
            const reason = cmd.payload?.reason || 'change';
            tdReason.textContent = translateReason(reason);
            tr.appendChild(tdReason);

            // 3. Длительность
            const tdDuration = document.createElement('td');
            tdDuration.textContent = calculateDuration(cmd.picked_at, cmd.finished_at, cmd.created_at, cmd.status);
            tr.appendChild(tdDuration);

            // 4. Статус
            const tdStatus = document.createElement('td');
            let statusText = 'В очереди';
            let statusColor = '#e4ddd6';
            let textColor = '#475569';

            if (cmd.status === 'processing') {
                statusText = 'В процессе';
                statusColor = '#ffe1b8';
                textColor = '#1e40af';
            } else if (cmd.status === 'done') {
                statusText = 'Выполнено';
                statusColor = '#dcfce7';
                textColor = '#15803d';
            } else if (cmd.status === 'failed') {
                statusText = 'Ошибка';
                statusColor = '#fee2e2';
                textColor = '#b91c1c';
            }

            const badge = document.createElement('span');
            badge.textContent = statusText;
            badge.style.background = statusColor;
            badge.style.color = textColor;
            badge.style.padding = '4px 10px';
            badge.style.borderRadius = '20px';
            badge.style.fontSize = '12px';
            badge.style.fontWeight = '600';
            badge.style.display = 'inline-block';
            tdStatus.appendChild(badge);
            tr.appendChild(tdStatus);

            // 5. Логи
            const tdLogs = document.createElement('td');
            if (cmd.result) {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'btn-secondary';
                btn.style.padding = '4px 10px';
                btn.style.fontSize = '12px';
                btn.textContent = '📄 Показать лог';
                btn.addEventListener('click', () => {
                    showHikvisionLog(cmd.id, cmd.created_at, cmd.result);
                });
                tdLogs.appendChild(btn);
            } else {
                tdLogs.textContent = '—';
                tdLogs.style.color = 'var(--theme-text-tertiary)';
            }
            tr.appendChild(tdLogs);

            body.appendChild(tr);
        });

    } catch (error) {
        console.error('Ошибка при загрузке истории:', error);
        body.innerHTML = `<tr><td colspan="5" style="text-align: center; color: #ef4444; padding: 20px;">Ошибка при загрузке данных: ${error.message}</td></tr>`;
    }
}

async function loadBridgeStatus() {
    const banner = document.getElementById('bridgeStatusBanner');
    if (!banner) return;
    if (document.getElementById('openDayState')) loadOpenDayState();

    try {
        const resp = await fetch('/api/hikvision/bridge/status');
        if (!resp.ok) throw new Error('Ошибка сети');
        const data = await resp.json();
        if (!data.success) throw new Error(data.message || 'Ошибка загрузки');

        const bridge = data.bridge;
        const queue = data.queue || {};
        const pending = queue.pending || 0;
        const processing = queue.processing;

        const queueMetric = document.getElementById('bridgeQueueMetric');
        if (queueMetric) queueMetric.textContent = processing ? `${pending} + 1` : String(pending);

        if (!bridge) {
            banner.style.borderColor = '#fecaca';
            banner.style.background = '#fff1f2';
            banner.innerHTML = `
                <div class="bridge-status-main">
                    <strong>Bridge не найден</strong><br>
                    <span style="font-size:13px;">Локальный bridge еще не отправлял heartbeat.</span>
                </div>
                ${bridgeStatusActionsHtml()}
            `;
            attachBridgeStatusButtons();
            setBridgeText('bridgeCpuMetric', '—');
            setBridgeText('bridgeCpuDetails', '');
            setBridgeText('bridgeRamMetric', '—');
            setBridgeText('bridgeRamDetails', '');
            setBridgeText('bridgeTempMetric', '—');
            setBridgeText('bridgeTempDetails', '');
            setBridgeText('bridgeDiskMetric', '—');
            setBridgeText('bridgeDiskDetails', '');
            setBridgeText('bridgeNetworkMetric', '—');
            setBridgeText('bridgeNetworkDetails', '');
            setBridgeText('bridgeHardwareMetric', '—');
            setBridgeText('bridgeHardwareDetails', '');
            setBridgeText('bridgeSensorMetric', '—');
            setBridgeText('bridgeSensorDetails', '');
            setBridgeText('bridgeUptimeMetric', '—');
            updateBridgeProgress(null);
            setBridgeLogs([]);
            return;
        }

        const online = data.online;
        const metrics = bridge.metrics || {};
        const hasLiveHeartbeat = !!(bridge.pid || metrics.cpu_used_percent != null || metrics.memory_used_percent != null || (Array.isArray(bridge.logs) && bridge.logs.length));
        const legacy = online && !hasLiveHeartbeat && (bridge.version === 'legacy-no-heartbeat' || bridge.reported_status === 'legacy');
        banner.style.borderColor = online ? (legacy ? '#fde68a' : '#bbf7d0') : '#fecaca';
        banner.style.background = online ? (legacy ? '#fffbeb' : '#f0fdf4') : '#fff1f2';
        const dot = online ? '●' : '●';
        const dotColor = online ? (legacy ? '#d96f00' : '#16a34a') : '#dc2626';
        const seenText = bridge.seconds_since_seen == null ? 'нет данных' : `${bridge.seconds_since_seen} сек назад`;
        banner.innerHTML = `
            <div class="bridge-status-main">
                <div style="display:flex; align-items:center; gap:8px; flex-wrap:wrap;">
                    <span style="color:${dotColor}; font-size:18px;">${dot}</span>
                    <strong>${online ? (legacy ? 'Bridge online, но старая версия' : 'Локальный Bridge online') : 'Локальный Bridge offline'}</strong>
                    <span style="color:var(--theme-text-secondary);">• ${escapeHtml(bridge.host || 'unknown')} • PID ${escapeHtml(bridge.pid || '—')}</span>
                </div>
                <div style="margin-top:6px; font-size:13px; color:var(--theme-text-secondary);">
                    Последний heartbeat: ${escapeHtml(seenText)}
                </div>
                ${legacy ? '<div style="margin-top:4px; font-size:13px; color:#92400e;">Обновите и перезапустите локальный bridge, чтобы появились live-логи и метрики.</div>' : ''}
                ${processing ? `<div style="margin-top:4px; font-size:13px;">Выполняется команда #${processing.id}</div>` : ''}
            </div>
            ${bridgeStatusActionsHtml()}
        `;
        attachBridgeStatusButtons();

        setBridgeText('bridgeCpuMetric', metrics.cpu_used_percent != null ? `${metrics.cpu_used_percent}%` : '—');
        setBridgeHtml('bridgeCpuDetails', bridgeMetricLines([
            ['Ядра', metrics.cpu_cores || '—'],
            ['Модель', metrics.cpu_model ? cleanCpuModel(metrics.cpu_model) : '—']
        ]));
        setBridgeMemory(metrics);
        setBridgeTemperature(metrics);
        setBridgeDisk(metrics.disk);
        setBridgeNetwork(metrics.network);
        setBridgeHardware(metrics.hardware);
        setBridgeSensors(metrics.temperatures);
        setBridgeText('bridgeUptimeMetric', formatUptime(bridge.uptime_seconds || 0));
        updateBridgeProgress(metrics.progress || null);
        setBridgeLogs(bridge.logs || []);
    } catch (error) {
        banner.style.borderColor = '#fecaca';
        banner.style.background = '#fff1f2';
        banner.innerHTML = `
            <div class="bridge-status-main">
                <strong>Ошибка загрузки bridge</strong><br>
                <span style="font-size:13px;">${escapeHtml(error.message)}</span>
            </div>
            ${bridgeStatusActionsHtml()}
        `;
        attachBridgeStatusButtons();
        updateBridgeProgress(null);
    }
}

function setBridgeText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = value;
}

function setBridgeHtml(id, value) {
    const el = document.getElementById(id);
    if (el) el.innerHTML = value || '';
}

function bridgeMetricLines(lines) {
    return lines
        .filter(([, value]) => value !== null && value !== undefined && value !== '')
        .map(([label, value]) => `
            <div class="bridge-metric-line">
                <span>${escapeHtml(label)}</span>
                <strong>${escapeHtml(value)}</strong>
            </div>
        `)
        .join('');
}

function setBridgeMemory(metrics) {
    setBridgeText('bridgeRamMetric', metrics.memory_used_percent != null ? `${metrics.memory_used_percent}%` : '—');
    const used = formatGbFromMb(metrics.memory_used_mb);
    const free = formatGbFromMb(metrics.memory_free_mb);
    const total = formatGbFromMb(metrics.memory_total_mb);
    setBridgeHtml('bridgeRamDetails', bridgeMetricLines([
        ['Занято', used || '—'],
        ['Свободно', free || '—'],
        ['Всего', total || '—']
    ]));
}

function setBridgeTemperature(metrics) {
    const temp = metrics.temperature_c ?? metrics.temperatures?.max_c;
    setBridgeText('bridgeTempMetric', temp != null ? `${temp}°C` : '—');
    const zones = Array.isArray(metrics.temperatures?.zones) ? metrics.temperatures.zones : [];
    const mainZones = zones
        .filter(zone => zone && zone.c != null)
        .slice(0, 2)
        .map(zone => [friendlySensorName(zone.name), `${zone.c}°C`]);
    setBridgeHtml('bridgeTempDetails', bridgeMetricLines([
        ['Макс', metrics.max_temperature_c != null ? `${metrics.max_temperature_c}°C` : '—'],
        ['CPU макс', metrics.max_cpu_temperature_c != null ? `${metrics.max_cpu_temperature_c}°C` : '—'],
        ...mainZones
    ]));
}

function setBridgeDisk(disk) {
    if (!disk) {
        setBridgeText('bridgeDiskMetric', '—');
        setBridgeText('bridgeDiskDetails', '');
        return;
    }
    setBridgeText('bridgeDiskMetric', disk.used_percent != null ? `${disk.used_percent}%` : '—');
    const primary = Array.isArray(disk.devices) && disk.devices[0] ? `${disk.devices[0].type} ${disk.devices[0].size_gb || ''}ГБ`.trim() : '';
    setBridgeHtml('bridgeDiskDetails', bridgeMetricLines([
        ['Занято', formatGb(disk.used_gb) || '—'],
        ['Свободно', formatGb(disk.free_gb) || '—'],
        ['Всего', formatGb(disk.total_gb) || '—'],
        ['Диск', primary || '—']
    ]));
}

function setBridgeNetwork(network) {
    if (!network) {
        setBridgeText('bridgeNetworkMetric', '—');
        setBridgeText('bridgeNetworkDetails', '');
        return;
    }
    setBridgeText('bridgeNetworkMetric', `↓ ${formatSpeed(network.download_mbps)}`);
    setBridgeHtml('bridgeNetworkDetails', bridgeMetricLines([
        ['Выгрузка', `↑ ${formatSpeed(network.upload_mbps)}`],
        ['Интерфейс', network.iface || 'сеть']
    ]));
}

function setBridgeHardware(hardware) {
    if (!hardware) {
        setBridgeText('bridgeHardwareMetric', '—');
        setBridgeText('bridgeHardwareDetails', '');
        return;
    }
    const board = hardware.board || hardware.product || '—';
    const usbCount = Array.isArray(hardware.usb_devices) ? hardware.usb_devices.length : 0;
    const netCount = Array.isArray(hardware.network_interfaces) ? hardware.network_interfaces.length : 0;
    setBridgeText('bridgeHardwareMetric', shortenText(board, 24));
    setBridgeHtml('bridgeHardwareDetails', bridgeMetricLines([
        ['USB', usbCount],
        ['LAN', netCount],
        ['BIOS', hardware.bios ? shortenText(hardware.bios, 18) : '—']
    ]));
}

function setBridgeSensors(temperatures) {
    const fans = Array.isArray(temperatures?.fans) ? temperatures.fans.filter(f => f.rpm != null && f.rpm > 0) : [];
    const voltages = Array.isArray(temperatures?.voltages) ? temperatures.voltages.filter(v => v.v != null && v.v > 0) : [];
    const fanText = fans.length ? `${fans[0].rpm} rpm` : '—';
    setBridgeText('bridgeSensorMetric', fanText);
    setBridgeHtml('bridgeSensorDetails', bridgeMetricLines([
        ['Кулер', fans.length ? `${fans.length} датч.` : 'нет данных'],
        ['Вольтаж', voltages[0] ? `${voltages[0].v}V` : 'нет данных']
    ]));
}

function bridgeStatusActionsHtml() {
    return `
        <div class="bridge-status-actions">
            <button type="button" id="hikvisionManualSyncBtn" class="bridge-status-icon-btn" title="Синхронизировать сейчас" aria-label="Синхронизировать сейчас">
                <i data-lucide="database-backup"></i>
            </button>
            <button type="button" id="bridgeUpdateBtn" class="bridge-status-icon-btn" title="Обновить код bridge и перезапустить" aria-label="Обновить код bridge и перезапустить">
                <i data-lucide="cloud-download"></i>
            </button>
            <button type="button" id="bridgeRestartBtn" class="bridge-status-icon-btn" title="Перезапустить bridge" aria-label="Перезапустить bridge">
                <i data-lucide="power"></i>
            </button>
            <button type="button" id="bridgeStatusRefreshBtn" class="bridge-status-icon-btn" title="Обновить статус" aria-label="Обновить статус">
                <i data-lucide="refresh-cw"></i>
            </button>
        </div>
    `;
}

function attachBridgeStatusButtons() {
    const syncBtn = document.getElementById('hikvisionManualSyncBtn');
    if (syncBtn && !syncBtn.dataset.bound) {
        syncBtn.dataset.bound = 'true';
        syncBtn.addEventListener('click', requestHikvisionSync);
    }
    const refreshBtn = document.getElementById('bridgeStatusRefreshBtn');
    if (refreshBtn && !refreshBtn.dataset.bound) {
        refreshBtn.dataset.bound = 'true';
        refreshBtn.addEventListener('click', loadBridgeStatus);
    }
    // Баннер перерисовывается при каждом обновлении статуса,
    // поэтому обработчики вешаем здесь, а не только при загрузке страницы.
    const updateBtn = document.getElementById('bridgeUpdateBtn');
    if (updateBtn && !updateBtn.dataset.bound) {
        updateBtn.dataset.bound = 'true';
        updateBtn.addEventListener('click', () => requestBridgeControl('update'));
    }
    const restartBtn = document.getElementById('bridgeRestartBtn');
    if (restartBtn && !restartBtn.dataset.bound) {
        restartBtn.dataset.bound = 'true';
        restartBtn.addEventListener('click', () => requestBridgeControl('restart'));
    }
    if (window.lucide) window.lucide.createIcons();
}

function formatGbFromMb(value) {
    if (value == null || !Number.isFinite(Number(value))) return '';
    return formatGb(Number(value) / 1024);
}

function formatGb(value) {
    if (value == null || !Number.isFinite(Number(value))) return '';
    return `${Number(value).toLocaleString('ru-RU', { maximumFractionDigits: 1 })} ГБ`;
}

function formatSpeed(mbps) {
    if (mbps == null || !Number.isFinite(Number(mbps))) return '—';
    return `${Number(mbps).toLocaleString('ru-RU', { maximumFractionDigits: 2 })} Мбит/с`;
}

function shortenText(text, max = 28) {
    const value = String(text || '').trim();
    return value.length > max ? `${value.slice(0, max - 1)}…` : value;
}

function cleanCpuModel(model) {
    return shortenText(String(model || '')
        .replace(/\(R\)|\(TM\)|CPU/gi, '')
        .replace(/\s*@\s*.+$/i, '')
        .replace(/\s+/g, ' ')
        .trim(), 24);
}

function friendlySensorName(name) {
    const value = String(name || '').toLowerCase();
    if (value.includes('x86_pkg') || value.includes('package')) return 'CPU пакет';
    if (value.includes('coretemp') || value.includes('cpu')) return 'CPU';
    if (value.includes('nvme')) return 'SSD';
    if (value.includes('acpitz')) return 'Система';
    return shortenText(String(name || 'Датчик').replace(/[_-]+/g, ' '), 16);
}

function setBridgeControlButtons(enabled, paused) {
    const pauseBtn = document.getElementById('bridgePauseBtn');
    const stopBtn = document.getElementById('bridgeStopBtn');
    const controls = document.getElementById('bridgeProgressControls');
    if (pauseBtn) {
        pauseBtn.dataset.action = paused ? 'resume' : 'pause';
        pauseBtn.textContent = paused ? '▶️ Продолжить запись' : '⏸️ Пауза записи';
        pauseBtn.disabled = !enabled;
        pauseBtn.style.display = enabled ? 'inline-flex' : 'none';
        pauseBtn.style.opacity = enabled ? '1' : '0.55';
        pauseBtn.style.cursor = enabled ? 'pointer' : 'not-allowed';
    }
    if (stopBtn) {
        stopBtn.disabled = !enabled;
        stopBtn.style.display = enabled ? 'inline-flex' : 'none';
        stopBtn.style.opacity = enabled ? '1' : '0.55';
        stopBtn.style.cursor = enabled ? 'pointer' : 'not-allowed';
    }
    if (controls) {
        const resultsBtn = document.getElementById('bridgeResultsBtn');
        const hasResultsButton = resultsBtn && resultsBtn.style.display !== 'none';
        controls.style.display = enabled || hasResultsButton ? 'flex' : 'none';
    }
}

function updateBridgeProgress(progress) {
    const panel = document.getElementById('bridgeProgressPanel');
    if (!panel) return;
    lastBridgeProgress = progress || null;

    if (!progress) {
        panel.style.display = 'none';
        renderBridgeDeviceProgress(null);
        const btn = document.getElementById('bridgeResultsBtn');
        if (btn) btn.style.display = 'none';
        setBridgeControlButtons(false, false);
        return;
    }

    const paused = !!progress.paused;
    const activeStages = new Set(['start', 'loading', 'devices_ready', 'device_start', 'probe', 'sync', 'clear_device']);
    const isActive = paused || activeStages.has(progress.stage || '');
    setBridgeControlButtons(isActive, paused);

    const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
    const processed = Number(progress.processed || 0);
    const total = Number(progress.total || 0);
    const stage = progress.stage || '';

    panel.style.display = 'block';
    setBridgeText('bridgeProgressTitle', stage === 'done' ? 'Синхронизация завершена' : (stage === 'stopped' ? 'Синхронизация остановлена' : 'Синхронизация Bridge'));
    setBridgeText('bridgeProgressPercent', `${percent}%`);
    const bar = document.getElementById('bridgeProgressBar');
    if (bar) {
        bar.style.width = `${percent}%`;
        bar.style.background = stage === 'error' || stage === 'stopped' ? '#dc2626' : (stage === 'done' ? '#16a34a' : (progress.paused ? '#ff8a00' : '#ff8a00'));
    }

    const status = cleanBridgeProgressStatus(progress.status_text || progress.current || 'Выполняется задача');
    const countText = total > 0 ? ` · ${processed} из ${total}` : '';
    setBridgeText('bridgeProgressText', `${status}${countText}`);

    const deviceList = Object.values(progress.devices || {});
    const aggregate = deviceList.reduce((acc, device) => {
        acc.success += Number(device.success || 0);
        acc.errors += Number(device.errors || 0);
        acc.rejected += Number(device.rejected || 0);
        return acc;
    }, { success: 0, errors: 0, rejected: 0 });
    const stats = [];
    if (progress.success != null || deviceList.length) stats.push(`успешно: ${progress.success ?? aggregate.success}`);
    if (progress.errors != null || deviceList.length) stats.push(`ошибок: ${progress.errors ?? aggregate.errors}`);
    if (progress.rejected != null || deviceList.length) stats.push(`отклонено: ${progress.rejected ?? aggregate.rejected}`);
    if (progress.skipped != null) stats.push(`заблокировано/пропущено: ${progress.skipped}`);
    const timingText = formatBridgeCompletionTiming(progress);
    if (timingText) stats.push(timingText);
    setBridgeText('bridgeProgressStats', stats.join(' · '));
    renderBridgeDeviceProgress(progress);

    const btn = document.getElementById('bridgeResultsBtn');
    if (btn) {
        const hasResults = Object.values(progress.devices || {}).some(device => {
            const results = device.results || {};
            return (results.success || []).length || (results.errors || []).length || (results.rejected || []).length;
        });
        btn.style.display = hasResults ? 'inline-flex' : 'none';
        const controls = document.getElementById('bridgeProgressControls');
        if (controls) controls.style.display = isActive || hasResults ? 'flex' : 'none';
    }
}

function cleanBridgeProgressStatus(text) {
    return String(text || '')
        .replace(/^(Вход|Выход)\s*\([^)]*\):\s*/i, '')
        .replace(/^(Вход|Выход):\s*/i, '')
        .replace(/\.?\s*Успешно\s+\d+\s*,?\s*ошибок\s+\d+\.?/i, '.')
        .replace(/\s{2,}/g, ' ')
        .replace(/\s+\./g, '.')
        .trim();
}

function formatBridgeCompletionTiming(progress) {
    if (!progress) return '';
    const stage = progress.stage || '';
    const finalStages = new Set(['done', 'done_with_errors']);
    const percent = Math.max(0, Math.min(100, Number(progress.percent || 0)));
    if (!finalStages.has(stage) && percent < 100) return '';

    const processed = Number(progress.processed || 0);
    if (!processed) return '';

    let durationMs = Number(progress.duration_ms || 0);
    if (!durationMs && progress.started_at && progress.finished_at) {
        const started = new Date(progress.started_at).getTime();
        const finished = new Date(progress.finished_at).getTime();
        if (Number.isFinite(started) && Number.isFinite(finished)) {
            durationMs = Math.max(0, finished - started);
        }
    }
    if (!durationMs) return '';

    const perRecordMs = durationMs / processed;
    return [
        `среднее: ${formatBridgeDuration(perRecordMs)} / 1 запись`,
        `${formatBridgeDuration(perRecordMs * 100)} / 100`,
        `всего: ${formatBridgeDuration(durationMs)}`
    ].join(' · ');
}

function formatBridgeDuration(ms) {
    const minutes = ms / 60000;
    if (minutes > 0 && minutes < 0.01) return '<0,01 мин';
    return `${formatBridgeDurationNumber(minutes)} мин`;
}

function formatBridgeDurationNumber(value) {
    if (value >= 10) return String(Math.round(value));
    if (value >= 1) return value.toFixed(1).replace('.', ',');
    return value.toFixed(2).replace('.', ',');
}

function renderBridgeDeviceProgress(progress) {
    const grid = document.getElementById('bridgeDeviceProgressGrid');
    if (!grid) return;
    const devices = Object.values(progress?.devices || {});
    if (!devices.length) {
        grid.innerHTML = '';
        return;
    }

    grid.innerHTML = devices.map(device => {
        const percent = Math.max(0, Math.min(100, Number(device.percent || 0)));
        const done = percent >= 100 || device.status === 'done' || device.stage === 'done';
        const isEntry = device.name === 'entry';
        const accent = done ? '#16a34a' : (isEntry ? '#ff8a00' : '#d96f00');
        const bg = done ? '#f0fdf4' : '#f7f4f1';
        const status = device.status === 'waiting' ? 'ожидает' : cleanBridgeProgressStatus(device.status_text || 'выполняется');
        return `
            <div style="border:1px solid ${accent}33; background:${bg}; border-radius:8px; padding:10px;">
                <div style="display:flex; justify-content:space-between; gap:8px; align-items:center;">
                    <strong style="color:${accent};">${escapeHtml(device.label || 'Терминал')}</strong>
                    <strong>${percent}%</strong>
                </div>
                <div style="height:8px; background:#e5e7eb; border-radius:999px; overflow:hidden; margin:8px 0;">
                    <div style="height:100%; width:${percent}%; background:${accent}; border-radius:999px;"></div>
                </div>
                <div style="font-size:12px; color:var(--theme-text-secondary);">${escapeHtml(status)}</div>
                <div style="font-size:12px; margin-top:5px;">
                    <span style="color:#16a34a;">успешно: ${Number(device.success || 0)}</span>
                    <span style="color:#dc2626; margin-left:8px;">ошибок: ${Number(device.errors || 0)}</span>
                    <span style="color:#92400e; margin-left:8px;">отклонено: ${Number(device.rejected || 0)}</span>
                </div>
            </div>
        `;
    }).join('');
}

function escapeHtml(value) {
    const div = document.createElement('div');
    div.textContent = String(value ?? '');
    return div.innerHTML;
}

function setBridgeLogs(logs) {
    const el = document.getElementById('bridgeLiveLogs');
    if (!el) return;
    const nearBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 20;
    if (!logs.length) {
        el.textContent = 'Логи пока не получены.';
        return;
    }
    el.innerHTML = logs.map(line => {
        const time = line.ts ? new Date(line.ts).toLocaleTimeString('ru-RU') : '';
        const message = formatBridgeLogMessage(line.message || '');
        const color = bridgeLogColor(line.level, message);
        return `<span style="color:${color};">${escapeHtml(`${time} ${bridgeLogLevelLabel(line.level)} ${message}`)}</span>`;
    }).join('\n');
    if (nearBottom) el.scrollTop = el.scrollHeight;
}

async function copyBridgeLiveLogs() {
    const el = document.getElementById('bridgeLiveLogs');
    const btn = document.getElementById('copyBridgeLogsBtn');
    const text = el?.innerText || '';
    if (!text.trim()) return;
    try {
        await navigator.clipboard.writeText(text);
        if (btn) {
            const previous = btn.innerHTML;
            btn.innerHTML = '<i data-lucide="check" style="width:14px; height:14px;"></i> Скопировано';
            if (window.lucide) window.lucide.createIcons();
            setTimeout(() => {
                btn.innerHTML = previous;
                if (window.lucide) window.lucide.createIcons();
            }, 1600);
        }
    } catch (error) {
        alert('Не удалось скопировать лог');
    }
}

function bridgeLogLevelLabel(level) {
    if (level === 'ERROR') return 'ОШИБКА';
    if (level === 'WARN') return 'ВНИМАНИЕ';
    return 'ИНФО';
}

function formatBridgeLogMessage(message) {
    let text = String(message || '');
    text = text.replace(/\[entry\]/gi, '[Вход]');
    text = text.replace(/\[exit\]/gi, '[Выход]');
    text = text.replace(/\bentry\b/gi, 'вход');
    text = text.replace(/\bexit\b/gi, 'выход');
    text = text.replace(/server command 502/gi, 'сервер Railway временно недоступен (502)');
    text = text.replace(/server command (\d+)/gi, 'сервер вернул ошибку $1');
    text = text.replace(/offline backoff active for (\d+)s/gi, 'терминал не отвечает, повторная попытка через $1 сек');
    text = text.replace(/reason=no_photo/gi, 'причина: нет фото');
    text = text.replace(/reason=([^,\s]+)/gi, 'причина: $1');
    text = text.replace(/paidThisMonth=(\d+)/gi, 'оплачено в этом месяце=$1');
    text = text.replace(/paid=(\d+)/gi, 'оплачено=$1');
    text = text.replace(/debt=(\d+)/gi, 'долг=$1');
    text = text.replace(/paymentExempt=(yes|true)/gi, 'льгота по оплате=да');
    text = text.replace(/paymentExempt=(no|false)/gi, 'льгота по оплате=нет');
    text = text.replace(/photo=(yes|true)/gi, 'фото=есть');
    text = text.replace(/photo=(no|false)/gi, 'фото=нет');
    text = text.replace(/\[sync\] summary \{"enabled":(\d+),"no_photo":(\d+)\}/i,
        '[sync] Итог списка: к записи готово $1, без фото $2');
    text = text.replace(/\[sync\] skip (.+)/i, '[sync] Пропущено: $1');
    text = text.replace(/\[bridge\] command polling (\d+)ms, daily full sync ([^ ]+) Asia\/Tashkent/i,
        'Bridge запущен. Проверка очереди каждые $1 мс, полная синхронизация в $2');
    text = text.replace(/\[bridge\] (\d+) Hikvision terminal\(s\) -> (.+)/i,
        'Bridge подключен к серверу $2. Терминалов: $1');
    text = text.replace(/\[sync\] (\d+) student\(s\), reason=(.+)/i,
        'Получено записей с сервера: $1. Причина: $2');
    text = text.replace(/\[([^\]]+)\] upserted face=already-exists (.+)/i,
        '[$1] Записан в терминал: $2 (фото уже было в терминале)');
    text = text.replace(/\[([^\]]+)\] upserted face=uploaded (.+)/i,
        '[$1] Записан в терминал: $2 (фото записано)');
    text = text.replace(/\[([^\]]+)\] (.+): fetch failed/i,
        '[$1] Ошибка записи: $2. Причина: соединение с терминалом оборвалось');
    text = text.replace(/EHOSTUNREACH/g, 'терминал недоступен по сети');
    text = text.replace(/ECONNREFUSED/g, 'терминал отклонил подключение');
    text = text.replace(/ETIMEDOUT/g, 'терминал не ответил вовремя');
    text = text.replace(/fetch failed/g, 'соединение с терминалом оборвалось');
    return text;
}

function bridgeLogColor(level, message) {
    if (level === 'ERROR' || /ОШИБКА|Ошибка/i.test(message)) return '#fecaca';
    if (/УСПЕШНО|успешно|Записан/i.test(message)) return '#bbf7d0';
    if (/Доступ закрыт|Отклонено|отклонено/i.test(message)) return '#fde68a';
    if (/\[Выход|Выход \(/i.test(message)) return '#ddd6fe';
    if (/\[Вход|Вход \(/i.test(message)) return '#ffe1b8';
    return '#e5eefb';
}

function openBridgeResultsModal() {
    const modal = document.getElementById('bridgeResultsModal');
    if (!modal) return;
    populateBridgeResultsDevices();
    renderBridgeResultsList();
    modal.style.display = 'block';
}

function populateBridgeResultsDevices() {
    const select = document.getElementById('bridgeResultsDeviceFilter');
    if (!select) return;
    const currentValue = select.value || 'all';
    const devices = Object.values(lastBridgeProgress?.devices || {});
    select.innerHTML = '<option value="all">Все терминалы</option>' + devices.map(device =>
        `<option value="${escapeHtml(device.key)}">${escapeHtml(device.label || device.key)}</option>`
    ).join('');
    select.value = Array.from(select.options).some(option => option.value === currentValue) ? currentValue : 'all';
}

function renderBridgeResultsList() {
    const list = document.getElementById('bridgeResultsList');
    if (!list) return;
    const deviceFilter = document.getElementById('bridgeResultsDeviceFilter')?.value || 'all';
    const type = document.getElementById('bridgeResultsTypeFilter')?.value || 'errors';
    const search = (document.getElementById('bridgeResultsSearch')?.value || '').trim().toLowerCase();
    const devices = Object.values(lastBridgeProgress?.devices || {})
        .filter(device => deviceFilter === 'all' || device.key === deviceFilter);

    const rows = [];
    devices.forEach(device => {
        const items = device.results?.[type] || [];
        items.forEach(item => {
            const text = `${item.employeeNo || ''} ${item.fullName || ''} ${item.reason || ''} ${item.detail || ''}`.toLowerCase();
            if (search && !text.includes(search)) return;
            rows.push({ device, item });
        });
    });

    if (!rows.length) {
        list.innerHTML = '<div style="padding:18px; color:var(--theme-text-secondary);">Записей нет.</div>';
        return;
    }

    const typeColor = type === 'success' ? '#16a34a' : (type === 'errors' ? '#dc2626' : '#92400e');
    const typeLabel = type === 'success' ? 'Успешно' : (type === 'errors' ? 'Ошибка' : 'Отклонено');
    list.innerHTML = rows.map(({ device, item }) => `
        <div class="bridge-result-row">
            <div class="bridge-result-device">${escapeHtml(device.label || device.key)}</div>
            <div>${escapeHtml(item.employeeNo || '—')}</div>
            <div>
                <div class="bridge-result-name">${escapeHtml(item.fullName || '—')}</div>
                <div class="bridge-result-detail">${escapeHtml(item.reason || item.detail || '')}</div>
            </div>
            <div class="bridge-result-status" style="color:${typeColor};">${typeLabel}</div>
        </div>
    `).join('');
}

function formatUptime(seconds) {
    const total = Number(seconds || 0);
    const days = Math.floor(total / 86400);
    const hours = Math.floor((total % 86400) / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    if (days > 0) return `${days}д ${hours}ч`;
    if (hours > 0) return `${hours}ч ${minutes}м`;
    return `${minutes}м`;
}

function formatDateTime(isoStr) {
    if (!isoStr) return '—';
    try {
        const date = new Date(isoStr);
        if (isNaN(date.getTime())) return isoStr;
        const day = String(date.getDate()).padStart(2, '0');
        const month = String(date.getMonth() + 1).padStart(2, '0');
        const year = date.getFullYear();
        const hours = String(date.getHours()).padStart(2, '0');
        const minutes = String(date.getMinutes()).padStart(2, '0');
        const seconds = String(date.getSeconds()).padStart(2, '0');
        return `${day}.${month}.${year} ${hours}:${minutes}:${seconds}`;
    } catch {
        return isoStr;
    }
}

function translateReason(reason) {
    if (!reason) return 'Автоматически';
    if (reason === 'manual') return 'Вручную (UI)';
    if (reason === 'settings_updated') return 'Обновление настроек';
    if (reason === 'startup') return 'Запуск моста';
    if (reason.startsWith('daily-')) {
        const time = document.getElementById('hikvision_daily_sync_time')?.value;
        return time ? `По расписанию (${time})` : 'По расписанию';
    }
    if (reason === 'student_created') return 'Новый ученик';
    if (reason === 'student_updated') return 'Ученик обновлен';
    if (reason === 'student_deleted') return 'Ученик удален';
    if (reason === 'student_photo_deleted') return 'Фото ученика удалено';
    if (reason === 'staff_created') return 'Новый сотрудник';
    if (reason === 'staff_updated') return 'Сотрудник обновлен';
    if (reason === 'staff_deleted') return 'Сотрудник удален';
    if (reason === 'payment_added') return 'Оплата добавлена';
    if (reason === 'payment_updated') return 'Оплата обновлена';
    if (reason === 'payment_deleted') return 'Оплата удалена';
    if (reason === 'payment_refunded') return 'Возврат оплаты';
    if (reason === 'monthly_payment_added') return 'Месячная оплата';
    if (reason === 'change') return 'Изменение данных';
    return reason;
}

function calculateDuration(pickedStr, finishedStr, createdStr, status) {
    if (status === 'pending') return 'В очереди...';
    if (status === 'processing') return 'Выполняется...';
    if (!finishedStr) return '—';

    const end = new Date(finishedStr);
    const start = new Date(pickedStr || createdStr);
    if (isNaN(end.getTime()) || isNaN(start.getTime())) return '—';

    const diffMs = end - start;
    if (diffMs < 0) return '—';

    const diffSeconds = Math.round(diffMs / 1000);
    if (diffSeconds < 60) {
        return `${diffSeconds} сек`;
    }
    const minutes = Math.floor(diffSeconds / 60);
    const seconds = diffSeconds % 60;
    return `${minutes} мин ${seconds} сек`;
}

function showHikvisionLog(id, createdTime, logText) {
    const modal = document.getElementById('hikvisionLogModal');
    const idSpan = document.getElementById('hikLogModalId');
    const timeSpan = document.getElementById('hikLogModalTime');
    const textEl = document.getElementById('hikLogModalText');

    if (modal && idSpan && timeSpan && textEl) {
        idSpan.textContent = `#${id}`;
        timeSpan.textContent = formatDateTime(createdTime);
        textEl.textContent = logText
            ? String(logText).split('\n').map(formatBridgeLogMessage).join('\n')
            : 'Нет записей в логе.';
        modal.style.display = 'block';
    }
}

// Экспортируем функцию глобально
window.loadSyncHistory = loadSyncHistory;
window.showHikvisionLog = showHikvisionLog;





// ============================================================
// Настройки карточки ученика: что показывать, а что скрыть
// ============================================================
let studentCardSectionsState = null;

function renderCardSectionsList(containerId, items, sections) {
    const container = document.getElementById(containerId);
    if (!container) return;
    container.innerHTML = items.map(item => {
        const enabled = sections[item.key] !== false;
        return `
            <label class="card-section-item${enabled ? '' : ' is-off'}" data-key="${escapeHtml(item.key)}">
                <input type="checkbox" data-section-key="${escapeHtml(item.key)}"${enabled ? ' checked' : ''}>
                <span>${escapeHtml(item.label)}</span>
            </label>
        `;
    }).join('');

    container.querySelectorAll('input[data-section-key]').forEach(input => {
        input.addEventListener('change', () => {
            const key = input.getAttribute('data-section-key');
            studentCardSectionsState.sections[key] = input.checked;
            input.closest('.card-section-item')?.classList.toggle('is-off', !input.checked);
        });
    });
}

async function loadStudentCardSections() {
    try {
        const response = await fetch('/api/settings/student-card');
        const data = await response.json();
        if (!data.success) throw new Error(data.message || 'Не удалось загрузить настройки');
        studentCardSectionsState = data;
        renderCardSectionsList('cardTabsList', data.tabs || [], data.sections || {});
        renderCardSectionsList('cardBlocksList', data.blocks || [], data.sections || {});
    } catch (error) {
        console.error('Настройки карточки ученика:', error);
        const container = document.getElementById('cardTabsList');
        if (container) container.innerHTML = `<div class="sc-empty">Ошибка: ${escapeHtml(error.message)}</div>`;
    }
}

async function saveStudentCardSections() {
    if (!studentCardSectionsState) return;
    try {
        const response = await fetch('/api/settings/student-card', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ sections: studentCardSectionsState.sections })
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.message || 'Не удалось сохранить');
        studentCardSectionsState.sections = data.sections;
        alert(data.message + '\n\nОткройте страницу учеников заново, чтобы увидеть изменения.');
    } catch (error) {
        alert('Ошибка: ' + error.message);
    }
}

function enableAllCardSections() {
    if (!studentCardSectionsState) return;
    Object.keys(studentCardSectionsState.sections).forEach(key => {
        studentCardSectionsState.sections[key] = true;
    });
    renderCardSectionsList('cardTabsList', studentCardSectionsState.tabs || [], studentCardSectionsState.sections);
    renderCardSectionsList('cardBlocksList', studentCardSectionsState.blocks || [], studentCardSectionsState.sections);
}

// Режим "пропустить всех": включается на сегодня и гаснет сам
async function loadOpenDayState() {
    const state = document.getElementById('openDayState');
    const onBtn = document.getElementById('openDayOnBtn');
    const offBtn = document.getElementById('openDayOffBtn');
    if (!state) return;

    try {
        const response = await fetch('/api/hikvision/open-day');
        const data = await response.json();
        if (!data.success) throw new Error(data.message || 'Не удалось получить состояние');

        if (data.active) {
            const until = data.open_until
                ? new Date(data.open_until).toLocaleDateString('ru-RU')
                : '';
            state.textContent = `Включен до ${until} включительно`;
            state.classList.add('is-active');
            if (onBtn) onBtn.hidden = true;
            if (offBtn) offBtn.hidden = false;
        } else {
            state.textContent = 'Выключен, действуют обычные правила';
            state.classList.remove('is-active');
            if (onBtn) onBtn.hidden = false;
            if (offBtn) offBtn.hidden = true;
        }
    } catch (error) {
        state.textContent = 'Не удалось получить состояние';
        console.error(error);
    }
}

async function setOpenDay(enable) {
    if (enable && !confirm(
        'Пропустить сегодня всех учеников?\n\n'
        + 'Оплата проверяться не будет, в терминалы уйдут все активные ученики с фото. '
        + 'Завтра правила вернутся автоматически.'
    )) return;

    try {
        const response = await fetch('/api/hikvision/open-day', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ enable })
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.message || 'Не удалось изменить режим');
        alert(data.message);
        loadOpenDayState();
        if (typeof loadBridgeStatus === 'function') setTimeout(loadBridgeStatus, 800);
    } catch (error) {
        alert('Ошибка: ' + error.message);
    }
}

// Автоархив: показываем, скольких затронет, и даем запустить вручную
async function refreshAutoArchivePreview() {
    const hint = document.getElementById('autoArchiveHint');
    const input = document.getElementById('auto_archive_after_months');
    if (!hint || !input) return;
    const preview = document.getElementById('autoArchivePreview');
    if (!Number(input.value)) {
        hint.dataset.preview = '';
        if (preview) preview.textContent = '';
        return;
    }
    try {
        const response = await fetch('/api/students/auto-archive/preview');
        const data = await response.json();
        if (!data.success || !data.enabled) return;
        const names = (data.candidates || []).slice(0, 5).map(item => item.full_name).join(', ');
        hint.dataset.preview = data.count
            ? `Сейчас под правило попадают ${data.count} учеников: ${names}${data.count > 5 ? ' и другие' : ''}`
            : 'Сейчас под правило никто не попадает';
        if (preview) preview.textContent = hint.dataset.preview;
    } catch (error) {
        console.error('Не удалось получить предпросмотр автоархива:', error);
    }
}

async function runAutoArchiveNow() {
    const input = document.getElementById('auto_archive_after_months');
    const months = Number(input?.value || 0);
    if (!months) {
        alert('Сначала укажите срок в месяцах и сохраните настройки.');
        return;
    }
    if (!confirm(
        `Перевести в архив всех, кто не приходил ${months} мес. и больше?\n\n`
        + 'Ученики останутся в списке со статусом «В архиве», их записи удалятся из терминалов. '
        + 'Вернуть можно в любой момент.'
    )) return;

    try {
        const response = await fetch('/api/students/auto-archive/run', { method: 'POST' });
        const data = await response.json();
        if (!data.success) throw new Error(data.message || 'Не удалось выполнить');
        alert(data.message);
        refreshAutoArchivePreview();
    } catch (error) {
        alert('Ошибка: ' + error.message);
    }
}

// ============================================================
// Вкладка "Не в терминале": кто не записан в Face ID и почему
// ============================================================

let terminalMissingData = null;
const terminalMissingSelection = new Set();
const terminalMissingFilters = { id: '', name: '', group: '', reason: '', paid: '', debt: '' };
let terminalMissingCategory = 'all';
let terminalMissingQuery = '';
let terminalMissingLoading = false;

const TERMINAL_MISSING_COLORS = {
    no_photo: '#d97706',
    photo_broken: '#b45309',
    payment: '#dc2626',
    inactive: '#64748b',
    sync_error: '#7c3aed',
};

async function loadTerminalMissing() {
    if (terminalMissingLoading) return;
    const body = document.getElementById('missingTableBody');
    if (!body) return;
    terminalMissingLoading = true;
    body.innerHTML = '<tr><td colspan="9" style="text-align:center; color:var(--theme-text-secondary); padding:20px;">Считаем список...</td></tr>';

    try {
        const response = await fetch('/api/hikvision/terminal-missing');
        const result = await response.json();
        if (!result.success) throw new Error(result.message || 'Не удалось получить список');
        terminalMissingData = result;
        const known = new Set((result.items || [])
            .filter(item => item.person_type === 'student')
            .map(item => item.person_id));
        Array.from(terminalMissingSelection)
            .filter(id => !known.has(id))
            .forEach(id => terminalMissingSelection.delete(id));
        ['fltGroup', 'fltReason', 'fltPaid'].forEach(id => {
            const el = document.getElementById(id);
            if (el) el.dataset.filled = 'false';
        });
        fillMissingFilterOptions();
        renderTerminalMissing();
    } catch (error) {
        body.innerHTML = `<tr><td colspan="9" style="text-align:center; color:#dc2626; padding:20px;">Ошибка: ${escapeHtml(error.message)}</td></tr>`;
    } finally {
        terminalMissingLoading = false;
    }
}

function matchesDebtRange(value, range) {
    if (!range) return true;
    const debt = Number(value || 0);
    if (range === '0') return debt <= 0;
    const [from, to] = range.split('-');
    if (from && debt < Number(from)) return false;
    if (to && debt > Number(to)) return false;
    return true;
}

function terminalMissingFilteredItems() {
    const items = terminalMissingData?.items || [];
    const query = terminalMissingQuery.trim().toLowerCase();
    const flt = terminalMissingFilters;

    return items.filter(item => {
        if (terminalMissingCategory !== 'all' && item.category !== terminalMissingCategory) return false;

        if (flt.id && !String(item.employee_no || '').includes(flt.id.trim())) return false;
        if (flt.name && !String(item.full_name || '').toLowerCase().includes(flt.name.trim().toLowerCase())) return false;
        if (flt.group && item.group !== flt.group) return false;
        if (flt.reason && item.reason !== flt.reason) return false;

        if (flt.paid === '__none__' && item.last_payment_date) return false;
        if (flt.paid && flt.paid !== '__none__' && item.last_payment_period !== flt.paid) return false;

        if (!matchesDebtRange(item.debt_amount, flt.debt)) return false;

        if (!query) return true;
        return [item.full_name, item.employee_no, item.group, item.reason_label, item.detail]
            .some(value => String(value || '').toLowerCase().includes(query));
    });
}

function fillMissingFilterOptions() {
    const items = terminalMissingData?.items || [];

    const groupSelect = document.getElementById('fltGroup');
    if (groupSelect && groupSelect.dataset.filled !== 'true') {
        const groups = [...new Set(items.map(item => item.group).filter(Boolean))].sort();
        groupSelect.innerHTML = '<option value="">Все группы</option>'
            + groups.map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join('');
        groupSelect.dataset.filled = 'true';
    }

    const reasonSelect = document.getElementById('fltReason');
    if (reasonSelect && reasonSelect.dataset.filled !== 'true') {
        const seen = new Map();
        items.forEach(item => { if (item.reason) seen.set(item.reason, item.reason_label); });
        reasonSelect.innerHTML = '<option value="">Все причины</option>'
            + [...seen.entries()].map(([value, label]) => `<option value="${escapeHtml(value)}">${escapeHtml(label)}</option>`).join('');
        reasonSelect.dataset.filled = 'true';
    }

    const paidSelect = document.getElementById('fltPaid');
    if (paidSelect && paidSelect.dataset.filled !== 'true') {
        const periods = [...new Set(items.map(item => item.last_payment_period).filter(Boolean))]
            .sort((a, b) => {
                const [am, ay] = a.split('.');
                const [bm, by] = b.split('.');
                return (by - ay) || (bm - am);
            });
        paidSelect.innerHTML = '<option value="">Любая оплата</option><option value="__none__">Не платили</option>'
            + periods.map(period => `<option value="${escapeHtml(period)}">за ${escapeHtml(period)}</option>`).join('');
        paidSelect.dataset.filled = 'true';
    }
}

function renderTerminalMissing() {
    const data = terminalMissingData;
    if (!data) return;

    const generated = document.getElementById('missingGeneratedAt');
    if (generated) {
        generated.textContent = data.generated_at
            ? `Обновлено: ${formatDateTime(data.generated_at)}`
            : '';
    }

    const summaryGrid = document.getElementById('missingSummaryGrid');
    if (summaryGrid) {
        const summary = data.summary || {};
        const cards = [
            { label: 'Всего людей', value: summary.total_people || 0, color: 'var(--theme-text-primary)' },
            { label: 'Записаны в терминал', value: summary.in_terminal || 0, color: '#16a34a' },
            { label: 'Нет в терминале', value: summary.missing || 0, color: '#dc2626' },
        ];
        summaryGrid.innerHTML = cards.map(card => `
            <div style="border:1px solid var(--theme-border); border-radius:8px; padding:12px; background:var(--theme-bg-secondary);">
                <div style="font-size:12px; color:var(--theme-text-secondary);">${escapeHtml(card.label)}</div>
                <div style="font-size:24px; font-weight:700; color:${card.color};">${card.value}</div>
            </div>
        `).join('');
    }

    const filters = document.getElementById('missingCategoryFilters');
    if (filters) {
        const categories = [{ category: 'all', label: 'Все причины', count: (data.items || []).length }]
            .concat(data.summary?.by_category || []);
        filters.innerHTML = categories.map(entry => {
            const active = terminalMissingCategory === entry.category;
            const color = TERMINAL_MISSING_COLORS[entry.category] || '#334155';
            return `
                <button type="button" class="btn-secondary" data-missing-category="${escapeHtml(entry.category)}"
                    style="padding:6px 12px; border-radius:999px; font-size:13px;
                    ${active ? `background:${color}; color:#fff; border-color:${color};` : ''}">
                    ${escapeHtml(entry.label)} · ${entry.count}
                </button>`;
        }).join('');
        filters.querySelectorAll('[data-missing-category]').forEach(button => {
            button.addEventListener('click', () => {
                terminalMissingCategory = button.getAttribute('data-missing-category');
                renderTerminalMissing();
            });
        });
    }

    const body = document.getElementById('missingTableBody');
    if (!body) return;
    const items = terminalMissingFilteredItems();
    if (!items.length) {
        // Пусто бывает и из-за фильтров — тогда это не «все записаны».
        const filtered = (data.items || []).length > 0;
        body.innerHTML = `<tr><td colspan="9" style="text-align:center; color:var(--theme-text-secondary); padding:20px;">${
            filtered ? 'Под фильтры никто не подходит — сбросьте фильтры.' : 'Никого нет — все записаны в терминал.'}</td></tr>`;
        updateMissingBulkBar();
        return;
    }

    body.innerHTML = items.map(item => {
        const color = TERMINAL_MISSING_COLORS[item.category] || '#334155';
        const photo = item.photo_url
            ? `<img src="${escapeHtml(item.photo_url)}" alt="" loading="lazy" style="width:40px; height:40px; border-radius:50%; object-fit:cover;">`
            : '<span style="display:inline-flex; width:40px; height:40px; border-radius:50%; background:#e2e8f0; align-items:center; justify-content:center; font-size:11px; color:#64748b;">нет</span>';
        const staffMark = item.person_type === 'staff'
            ? ' <span style="font-size:11px; color:var(--theme-text-secondary);">(сотрудник)</span>'
            : '';
        const period = item.last_payment_period
            ? ` <span style="font-size:11px; color:var(--theme-text-secondary);">за ${escapeHtml(item.last_payment_period)}</span>`
            : '';
        const selectable = item.person_type === 'student';
        const checked = terminalMissingSelection.has(item.person_id) ? ' checked' : '';
        return `
            <tr class="${selectable ? 'is-selectable' : ''}">
                <td>${selectable
                    ? `<input type="checkbox" class="missing-row-check" data-student-id="${item.person_id}"${checked}>`
                    : ''}</td>
                <td>${photo}</td>
                <td>${escapeHtml(item.employee_no)}</td>
                <td>${escapeHtml(item.full_name)}${staffMark}</td>
                <td>${escapeHtml(item.group || '—')}</td>
                <td><span style="color:${color}; font-weight:600;">${escapeHtml(item.reason_label)}</span></td>
                <td class="missing-paid-cell">
                    ${item.last_payment_date
                        ? `<span class="missing-paid-sum">${formatTerminalMissingSum(item.last_payment_amount)}</span>
                           <span class="missing-paid-date">${escapeHtml(item.last_payment_date)}${period}</span>`
                        : '—'}
                </td>
                <td style="white-space:nowrap; font-weight:600; color:#dc2626;">${Number(item.debt_amount || 0) > 0 ? formatTerminalMissingSum(item.debt_amount) : '—'}</td>
                <td class="missing-row-actions">
                    ${selectable ? `
                        <button type="button" class="missing-row-menu-btn" title="Действия"
                            onclick="toggleMissingRowMenu(event, ${item.person_id})">
                            <i data-lucide="more-vertical"></i>
                        </button>
                        <div class="missing-row-menu" id="missingRowMenu_${item.person_id}">
                            <button type="button" onclick="openBulkTariffModal([${item.person_id}])">
                                <i data-lucide="credit-card"></i> Изменить тариф
                            </button>
                            <button type="button" onclick="redistributePayments([${item.person_id}])">
                                <i data-lucide="arrow-left-right"></i> Перенести оплаты назад
                            </button>
                        </div>` : ''}
                </td>
            </tr>`;
    }).join('');

    body.querySelectorAll('.missing-row-check').forEach(checkbox => {
        checkbox.addEventListener('change', () => {
            const id = Number(checkbox.getAttribute('data-student-id'));
            if (checkbox.checked) terminalMissingSelection.add(id);
            else terminalMissingSelection.delete(id);
            updateMissingBulkBar();
        });
    });
    updateMissingBulkBar();
    if (window.lucide) window.lucide.createIcons();
}

function missingSelectableItems() {
    return terminalMissingFilteredItems().filter(item => item.person_type === 'student');
}

function updateMissingBulkBar() {
    const bar = document.getElementById('missingBulkBar');
    const counter = document.getElementById('missingSelectedCount');
    if (counter) counter.textContent = String(terminalMissingSelection.size);
    if (bar) bar.hidden = terminalMissingSelection.size === 0;

    const selectAll = document.getElementById('missingSelectAll');
    if (selectAll) {
        const visible = missingSelectableItems();
        const selectedVisible = visible.filter(item => terminalMissingSelection.has(item.person_id));
        selectAll.checked = visible.length > 0 && selectedVisible.length === visible.length;
        selectAll.indeterminate = selectedVisible.length > 0 && selectedVisible.length < visible.length;
    }
}

async function loadBulkTariffOptions() {
    const select = document.getElementById('bulkTariffSelect');
    if (!select || select.dataset.loaded === 'true') return;
    try {
        const response = await fetch('/api/tariffs');
        const tariffs = await response.json();
        select.innerHTML = '<option value="">Без тарифа</option>' + (tariffs || [])
            .map(tariff => `<option value="${tariff.id}" data-price="${Number(tariff.price) || 0}">${escapeHtml(tariff.name)} — ${Number(tariff.price || 0).toLocaleString('ru-RU')} сум</option>`)
            .join('');
        select.dataset.loaded = 'true';
    } catch (error) {
        console.error('Не удалось загрузить тарифы:', error);
    }
}

let bulkTariffTargetIds = [];

function toggleMissingRowMenu(event, studentId) {
    event.stopPropagation();
    const menu = document.getElementById(`missingRowMenu_${studentId}`);
    if (!menu) return;
    const wasOpen = menu.classList.contains('open');
    document.querySelectorAll('.missing-row-menu.open').forEach(el => el.classList.remove('open'));
    if (!wasOpen) menu.classList.add('open');
}

document.addEventListener('click', () => {
    document.querySelectorAll('.missing-row-menu.open').forEach(el => el.classList.remove('open'));
});

async function openBulkTariffModal(ids) {
    bulkTariffTargetIds = Array.isArray(ids) && ids.length ? ids : Array.from(terminalMissingSelection);
    if (!bulkTariffTargetIds.length) return;
    await loadBulkTariffOptions();

    const counter = document.getElementById('bulkTariffCount');
    if (counter) counter.textContent = String(bulkTariffTargetIds.length);

    // Подставляем текущий тариф. Если у выбранных он разный - оставляем пустым.
    const items = (terminalMissingData?.items || [])
        .filter(item => bulkTariffTargetIds.includes(item.person_id));
    const tariffIds = [...new Set(items.map(item => item.tariff_id ?? ''))];
    const select = document.getElementById('bulkTariffSelect');
    const hint = document.getElementById('bulkTariffCurrent');

    if (select) select.value = tariffIds.length === 1 ? String(tariffIds[0] ?? '') : '';
    if (hint) {
        if (tariffIds.length === 1) {
            const name = items[0]?.tariff_name || 'Без тарифа';
            hint.textContent = `Сейчас: ${name}`;
        } else {
            hint.textContent = `У выбранных учеников тарифы разные (${tariffIds.length})`;
        }
    }

    document.getElementById('bulkTariffModal').style.display = 'block';
}

async function applyBulkTariff() {
    const select = document.getElementById('bulkTariffSelect');
    const clubFunded = document.getElementById('bulkTariffClubFunded');
    const ids = bulkTariffTargetIds.length ? bulkTariffTargetIds : Array.from(terminalMissingSelection);
    if (!ids.length) return;

    const payload = { student_ids: ids, tariff_id: select.value || null };
    if (clubFunded && clubFunded.checked) payload.club_funded = true;

    try {
        const response = await fetch('/api/students/bulk/tariff', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (!result.success) throw new Error(result.message || 'Не удалось сменить тариф');

        // Показываем, кого новый тариф уже пропускает, а кто остался должником
        let report = result.message;
        const blocked = result.still_blocked || [];
        if (blocked.length) {
            const lines = blocked.slice(0, 12).map(item => {
                const debt = item.debt
                    ? ` (долг ${Math.round(item.debt).toLocaleString('ru-RU')} сум)`
                    : '';
                return `\u2022 ${item.full_name} \u2014 ${item.reason_label}${debt}`;
            });
            if (blocked.length > 12) lines.push(`\u2026 и еще ${blocked.length - 12}`);
            report += '\n\nОстаются закрытыми:\n' + lines.join('\n');
        }
        alert(report);
        document.getElementById('bulkTariffModal').style.display = 'none';
        terminalMissingSelection.clear();
        loadTerminalMissing();
    } catch (error) {
        alert('Ошибка: ' + error.message);
    }
}

async function redistributePayments(ids) {
    ids = Array.isArray(ids) && ids.length ? ids : Array.from(terminalMissingSelection);
    if (!ids.length) return;
    if (!confirm(
        `Перенести оплаты на более ранние месяцы у ${ids.length} учеников?\n\n` +
        'Общая сумма оплат не изменится: деньги закроют старые месяцы, ' +
        'а долг соберется в самых свежих. Это уменьшает число месяцев долга.'
    )) return;

    try {
        const response = await fetch('/api/students/bulk/redistribute-payments', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ student_ids: ids })
        });
        const result = await response.json();
        if (!result.success) throw new Error(result.message || 'Не удалось перераспределить оплаты');
        alert(result.message);
        terminalMissingSelection.clear();
        loadTerminalMissing();
    } catch (error) {
        alert('Ошибка: ' + error.message);
    }
}

function formatTerminalMissingSum(value) {
    if (value === null || value === undefined || value === '') return '—';
    const amount = Number(value);
    if (!Number.isFinite(amount)) return '—';
    return `${Math.round(amount).toLocaleString('ru-RU').replace(/\u00a0/g, ' ')} сум`;
}

function exportTerminalMissingCsv() {
    const items = terminalMissingFilteredItems();
    if (!items.length) {
        alert('Список пуст — нечего выгружать.');
        return;
    }
    const header = ['ID', 'ФИО', 'Группа', 'Тип', 'Причина',
        'Дата последней оплаты', 'За период', 'Сумма оплаты', 'Долг', 'Подробности'];
    const rows = items.map(item => [
        item.employee_no,
        item.full_name,
        item.group || '',
        item.person_type === 'staff' ? 'Сотрудник' : 'Ученик',
        item.reason_label,
        item.last_payment_date || '',
        item.last_payment_period || '',
        item.last_payment_amount == null ? '' : Math.round(Number(item.last_payment_amount)),
        Math.round(Number(item.debt_amount || 0)),
        item.detail || '',
    ]);
    const csv = [header].concat(rows)
        .map(row => row.map(cell => `"${String(cell).replace(/"/g, '""')}"`).join(';'))
        .join('\r\n');
    const blob = new Blob(['﻿' + csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'ne-v-terminale.csv';
    link.click();
    URL.revokeObjectURL(url);
}

document.addEventListener('DOMContentLoaded', () => {
    const refreshBtn = document.getElementById('missingRefreshBtn');
    if (refreshBtn) refreshBtn.addEventListener('click', () => loadTerminalMissing());

    const exportBtn = document.getElementById('missingExportBtn');
    if (exportBtn) exportBtn.addEventListener('click', exportTerminalMissingCsv);

    const cardSaveBtn = document.getElementById('cardSectionsSaveBtn');
    if (cardSaveBtn) cardSaveBtn.addEventListener('click', saveStudentCardSections);
    const cardAllBtn = document.getElementById('cardSectionsAllBtn');
    if (cardAllBtn) cardAllBtn.addEventListener('click', enableAllCardSections);

    const openDayOnBtn = document.getElementById('openDayOnBtn');
    if (openDayOnBtn) openDayOnBtn.addEventListener('click', () => setOpenDay(true));
    const openDayOffBtn = document.getElementById('openDayOffBtn');
    if (openDayOffBtn) openDayOffBtn.addEventListener('click', () => setOpenDay(false));

    const autoArchiveBtn = document.getElementById('autoArchiveRunBtn');
    if (autoArchiveBtn) autoArchiveBtn.addEventListener('click', runAutoArchiveNow);

    const search = document.getElementById('missingSearchInput');
    if (search) {
        search.addEventListener('input', () => {
            terminalMissingQuery = search.value || '';
            renderTerminalMissing();
        });
    }

    const selectAll = document.getElementById('missingSelectAll');
    if (selectAll) {
        selectAll.addEventListener('change', () => {
            const visible = missingSelectableItems();
            if (selectAll.checked) visible.forEach(item => terminalMissingSelection.add(item.person_id));
            else visible.forEach(item => terminalMissingSelection.delete(item.person_id));
            renderTerminalMissing();
        });
    }

    const clearBtn = document.getElementById('missingBulkClearBtn');
    if (clearBtn) {
        clearBtn.addEventListener('click', () => {
            terminalMissingSelection.clear();
            renderTerminalMissing();
        });
    }

    const tariffBtn = document.getElementById('missingBulkTariffBtn');
    if (tariffBtn) tariffBtn.addEventListener('click', () => openBulkTariffModal(Array.from(terminalMissingSelection)));

    const applyTariffBtn = document.getElementById('bulkTariffApplyBtn');
    if (applyTariffBtn) applyTariffBtn.addEventListener('click', applyBulkTariff);

    const redistributeBtn = document.getElementById('missingBulkRedistributeBtn');
    if (redistributeBtn) redistributeBtn.addEventListener('click', () => redistributePayments(Array.from(terminalMissingSelection)));

    const filterMap = {
        fltId: 'id',
        fltName: 'name',
        fltGroup: 'group',
        fltReason: 'reason',
        fltPaid: 'paid',
        fltDebt: 'debt',
    };
    Object.entries(filterMap).forEach(([elementId, key]) => {
        const el = document.getElementById(elementId);
        if (!el) return;
        const eventName = el.tagName === 'SELECT' ? 'change' : 'input';
        el.addEventListener(eventName, () => {
            terminalMissingFilters[key] = el.value || '';
            renderTerminalMissing();
        });
    });

    const resetBtn = document.getElementById('fltReset');
    if (resetBtn) {
        resetBtn.addEventListener('click', () => {
            Object.keys(terminalMissingFilters).forEach(key => { terminalMissingFilters[key] = ''; });
            Object.keys(filterMap).forEach(elementId => {
                const el = document.getElementById(elementId);
                if (el) el.value = '';
            });
            terminalMissingQuery = '';
            const search = document.getElementById('missingSearchInput');
            if (search) search.value = '';
            terminalMissingCategory = 'all';
            renderTerminalMissing();
        });
    }
});

window.loadTerminalMissing = loadTerminalMissing;
