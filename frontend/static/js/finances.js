// Сохранение активной вкладки в localStorage
const financeEditIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';
const financeTrashIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5"/><path d="M14 11v5"/></svg>';

function saveActiveFinancesTab(tabName) {
    localStorage.setItem('finances_active_tab', tabName);
}

// Восстановление активной вкладки из localStorage
function restoreActiveFinancesTab() {
    const savedTab = localStorage.getItem('finances_active_tab');
    if (savedTab) {
        // Небольшая задержка для загрузки DOM
        setTimeout(() => {
            const tab = document.querySelector(`.tab[data-tab="${savedTab}"]`);
            if (tab) {
                // Убрать активный класс со всех вкладок
                document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
                document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));

                // Активировать сохраненную вкладку
                tab.classList.add('active');
                const tabName = savedTab;
                const actualTabName = tabName === 'balance' ? 'balance' : tabName;
                const tabElement = document.getElementById(`${actualTabName}-tab`);
                if (tabElement) {
                    tabElement.classList.add('active');
                }

                // Показать/скрыть кнопки в зависимости от активной вкладки
                const incomeButtons = document.getElementById('income-tab-buttons');
                if (incomeButtons) {
                    incomeButtons.style.display = tabName === 'income' ? 'flex' : 'none';
                }

                const expensesButtons = document.getElementById('expenses-tab-buttons');
                if (expensesButtons) {
                    expensesButtons.style.display = tabName === 'expenses' ? 'flex' : 'none';
                }

                const cashButtons = document.getElementById('cash-tab-buttons');
                if (cashButtons) {
                    cashButtons.style.display = tabName === 'cash' ? 'flex' : 'none';
                }

                // Загрузить данные для вкладки, если нужно
                if (tabName === 'cash' && typeof loadCashTransfers === 'function' && typeof loadCashBalance === 'function') {
                    setTimeout(() => {
                        loadCashBalance();
                        loadCashTransfers();
                    }, 100);
                } else if (tabName === 'debtors' && typeof loadDebtors === 'function') {
                    setTimeout(() => {
                        loadDebtors();
                    }, 100);
                }
            }
        }, 100);
    }
}

// Переключение вкладок
document.querySelectorAll('.tab').forEach(tab => {
    tab.addEventListener('click', () => {
        const tabName = tab.getAttribute('data-tab');

        // Сохранить активную вкладку
        saveActiveFinancesTab(tabName);

        // Убрать активный класс со всех вкладок
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));

        // Активировать выбранную вкладку
        tab.classList.add('active');

        // Обработать вкладку "balance" как "debtors" для совместимости
        const actualTabName = tabName === 'balance' ? 'balance' : tabName;
        const tabElement = document.getElementById(`${actualTabName}-tab`);
        if (tabElement) {
            tabElement.classList.add('active');
        }

        // Показать/скрыть кнопки в зависимости от активной вкладки
        const incomeButtons = document.getElementById('income-tab-buttons');
        if (incomeButtons) {
            incomeButtons.style.display = tabName === 'income' ? 'flex' : 'none';
        }

        const expensesButtons = document.getElementById('expenses-tab-buttons');
        if (expensesButtons) {
            expensesButtons.style.display = tabName === 'expenses' ? 'flex' : 'none';
        }

        const cashButtons = document.getElementById('cash-tab-buttons');
        if (cashButtons) {
            cashButtons.style.display = tabName === 'cash' ? 'flex' : 'none';
        }

        // Загрузить данные кассы при переключении на вкладку
        if (tabName === 'cash' && typeof loadCashTransfers === 'function' && typeof loadCashBalance === 'function') {
            setTimeout(() => {
                loadCashBalance();
                loadCashTransfers();
            }, 100);
        }
    });
});

// Показать кнопки при загрузке страницы, если активна соответствующая вкладка
document.addEventListener('DOMContentLoaded', () => {
    // Проверить хэш в URL для автоматического переключения на вкладку
    const hash = window.location.hash.substring(1); // убираем #
    let activeTabName = null;

    // Сначала проверить сохраненную вкладку, если нет хэша в URL
    if (!hash) {
        restoreActiveFinancesTab();
        // Получить активную вкладку после восстановления
        const activeTab = document.querySelector('.tab.active');
        if (activeTab) {
            activeTabName = activeTab.getAttribute('data-tab');
        }
    } else if (hash === 'cash') {
        activeTabName = 'cash';
        // Переключить на вкладку cash
        document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(tc => tc.classList.remove('active'));

        const cashTab = document.querySelector('.tab[data-tab="cash"]');
        const cashContent = document.getElementById('cash-tab');
        if (cashTab && cashContent) {
            cashTab.classList.add('active');
            cashContent.classList.add('active');
        }
        saveActiveFinancesTab('cash');
    }

    const activeTab = document.querySelector('.tab.active');
    if (activeTab) {
        const tabName = activeTab.getAttribute('data-tab');
        const incomeButtons = document.getElementById('income-tab-buttons');
        const expensesButtons = document.getElementById('expenses-tab-buttons');
        const cashButtons = document.getElementById('cash-tab-buttons');

        if (tabName === 'income' && incomeButtons) {
            incomeButtons.style.display = 'flex';
        }
        if (tabName === 'expenses' && expensesButtons) {
            expensesButtons.style.display = 'flex';
        }
        if (tabName === 'cash' && cashButtons) {
            cashButtons.style.display = 'flex';
        }
    }
});

// Хранилище данных прихода/расходов
let allIncomeData = [];
let allExpenseData = [];
let incomeDefaultFilterApplied = false;
let expenseDefaultFilterApplied = false;

const defaultExpenseCategories = ['Аренда', 'Зарплата', 'Оборудование', 'Коммунальные', 'Ремонт стадиона', 'Оплата за сайт', 'Дивидент', 'Инкасация', 'Прочее'];
const expenseCategoryState = { loaded: false, list: [] };
const expenseCategoryColors = {};
const expenseColorPalette = [
    '#ff8a00', '#d96f00', '#EC4899', '#ff8a00', '#10B981', '#0EA5E9', '#ff8a00', '#14B8A6', '#84CC16', '#E11D48'
];

function normalizeExpenseCategories(list) {
    const uniq = new Set();
    (list || []).forEach((item) => {
        const value = (item || '').toString().trim();
        // Пропускаем "Другое" и техническую категорию "Encashment"
        if (value && value !== 'Другое' && value !== 'Encashment') {
            uniq.add(value);
        }
    });
    return Array.from(uniq);
}

async function loadExpenseCategoriesFromSettings() {
    if (expenseCategoryState.loaded && expenseCategoryState.list.length) {
        return expenseCategoryState.list;
    }

    try {
        const resp = await fetch('/api/club-settings');
        const data = await resp.json();
        const categories = Array.isArray(data.expense_categories) ? data.expense_categories : [];
        expenseCategoryState.list = normalizeExpenseCategories(categories);
    } catch (error) {
        console.error('Ошибка загрузки статей расхода:', error);
    }

    if (!expenseCategoryState.list.length) {
        expenseCategoryState.list = [...defaultExpenseCategories];
    }

    // Гарантируем наличие Инкасации
    if (!expenseCategoryState.list.includes('Инкасация')) {
        expenseCategoryState.list.push('Инкасация');
    }
    if (!expenseCategoryState.list.includes('Оплата за сайт')) {
        expenseCategoryState.list.splice(Math.max(expenseCategoryState.list.indexOf('Ремонт стадиона') + 1, 0), 0, 'Оплата за сайт');
    }

    expenseCategoryState.loaded = true;
    return expenseCategoryState.list;
}

function populateExpenseCategorySelect(selectId, categories, options = {}) {
    const select = document.getElementById(selectId);
    if (!select) return;

    const { includeAll = false, includeOther = false } = options;
    const currentValue = select.value;

    select.innerHTML = '';

    if (includeAll) {
        const opt = document.createElement('option');
        opt.value = '';
        opt.textContent = 'Все категории';
        select.appendChild(opt);
    }

    categories.forEach((cat) => {
        const opt = document.createElement('option');
        opt.value = cat;
        opt.textContent = cat;
        select.appendChild(opt);
    });

    if (includeOther) {
        const opt = document.createElement('option');
        opt.value = 'Другое';
        opt.textContent = 'Другое';
        select.appendChild(opt);
    }

    const hasCurrent = Array.from(select.options).some(o => o.value === currentValue);
    if (hasCurrent) {
        select.value = currentValue;
    }
}

async function ensureExpenseCategoryOptions(extraCategories = []) {
    const baseCategories = await loadExpenseCategoriesFromSettings();
    // Фильтруем техническую категорию "Encashment" - она не должна показываться пользователю
    const filteredExtra = (extraCategories || []).filter(cat => cat !== 'Encashment');
    const merged = normalizeExpenseCategories([...baseCategories, ...filteredExtra]);

    populateExpenseCategorySelect('add-expense-category', merged, { includeOther: true });
    populateExpenseCategorySelect('edit-category', merged, { includeOther: true });
    populateExpenseCategorySelect('expense-category-filter', merged, { includeAll: true, includeOther: true });
}

function getExpenseCategoryColor(category) {
    if (expenseCategoryColors[category]) return expenseCategoryColors[category];
    const index = Object.keys(expenseCategoryColors).length % expenseColorPalette.length;
    expenseCategoryColors[category] = expenseColorPalette[index];
    return expenseCategoryColors[category];
}

// Загрузка данных прихода
async function loadIncome() {
    try {
        const response = await fetch('/api/finances/income');
        const data = await response.json();
        allIncomeData = data.payments || [];

        // Статистика (элементы удалены из UI, но данные остаются для возможного использования)
        const incomeTodayEl = document.getElementById('income-today');
        const incomeMonthEl = document.getElementById('income-month');
        const incomeTotalEl = document.getElementById('income-total');
        if (incomeTodayEl) incomeTodayEl.textContent = data.today.toLocaleString('ru-RU') + ' сум';
        if (incomeMonthEl) incomeMonthEl.textContent = data.month.toLocaleString('ru-RU') + ' сум';
        if (incomeTotalEl) incomeTotalEl.textContent = data.total.toLocaleString('ru-RU') + ' сум';

        if (!incomeDefaultFilterApplied) {
            const todayDate = new Date();
            const startOfMonth = new Date(todayDate.getFullYear(), todayDate.getMonth(), 1).toISOString().split('T')[0];
            const today = todayDate.toISOString().split('T')[0];
            const fromInput = document.getElementById('income-date-from');
            const toInput = document.getElementById('income-date-to');
            if (fromInput && !fromInput.value) fromInput.value = startOfMonth;
            if (toInput && !toInput.value) toInput.value = today;
            incomeDefaultFilterApplied = true;
            await filterIncome(true);
        } else {
            renderIncomeTable(allIncomeData);
        }
    } catch (error) {
        console.error('Ошибка загрузки прихода:', error);
    }
}

// Загрузка должников
async function loadDebtors() {
    try {
        const response = await fetch('/api/finances/debtors');
        const data = await response.json();

        // Статистика
        document.getElementById('total-debt').textContent = data.total_debt.toLocaleString('ru-RU') + ' сум';
        document.getElementById('debtors-count').textContent = data.count;

        renderDebtorsAccordion(data.debtors || []);
    } catch (error) {
        console.error('Ошибка загрузки должников:', error);
    }
}

function renderDebtorsAccordion(debtors) {
    const container = document.getElementById('debtors-accordion');
    if (!container) return;

    if (!debtors.length) {
        container.innerHTML = '<div class="info-text" style="text-align:center; padding:16px; color:#27ae60;">Нет должников 🎉</div>';
        return;
    }

    const grouped = debtors.reduce((acc, d) => {
        const key = d.student_id || `${d.student_name}|${d.student_phone || ''}`;
        if (!acc[key]) {
            acc[key] = {
                student_name: d.student_name,
                student_phone: d.student_phone || '-',
                total_due: 0,
                items: []
            };
        }
        acc[key].total_due += Number(d.amount_due || 0);
        acc[key].items.push(d);
        return acc;
    }, {});

    const groups = Object.values(grouped);
    container.innerHTML = groups.map((g, idx) => {
        const rows = g.items.map(item => {
            return `
                <div class="debt-row">
                    <div>
                        <div class="label">Месяц</div>
                        <div class="value"><span style="background: #fff3cd; padding: 4px 8px; border-radius: 6px; font-weight:700; color:#92400e;">${item.month_label}</span></div>
                    </div>
                    <div>
                        <div class="label">Тариф</div>
                        <div class="value">${item.tariff_name || '-'}${item.tariff_price ? ' — ' + Number(item.tariff_price).toLocaleString('ru-RU') + ' сум' : ''}</div>
                    </div>
                    <div>
                        <div class="label">Оплачено</div>
                        <div class="value">${Number(item.amount_paid || 0).toLocaleString('ru-RU')} сум</div>
                    </div>
                    <div>
                        <div class="label">Долг</div>
                        <div class="value"><span class="debt-badge">${Number(item.amount_due || 0).toLocaleString('ru-RU')} сум</span></div>
                    </div>
                </div>
            `;
        }).join('');

        return `
            <div class="debt-accordion-item ${idx === 0 ? 'open' : ''}">
                <div class="debt-accordion-header">
                    <div class="student-info">
                        <div class="student-name">${escapeHtml(g.student_name)}</div>
                        <div class="student-phone">${escapeHtml(g.student_phone)}</div>
                    </div>
                    <div style="display:flex; align-items:center; gap:12px;">
                        <span class="badge-count">${g.items.length} мес.</span>
                        <div class="debt-total">${g.total_due.toLocaleString('ru-RU')} сум</div>
                        <svg class="chevron" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" style="color: var(--theme-text-secondary); transition: transform 0.2s; ${idx === 0 ? 'transform: rotate(180deg);' : ''}"><polyline points="18 15 12 9 6 15"></polyline></svg>
                    </div>
                </div>
                <div class="debt-accordion-body">
                    <div class="debt-rows">${rows}</div>
                </div>
            </div>
        `;
    }).join('');

    container.querySelectorAll('.debt-accordion-header').forEach(header => {
        header.addEventListener('click', () => {
            const item = header.parentElement;
            const isOpen = item.classList.contains('open');
            // close others
            container.querySelectorAll('.debt-accordion-item').forEach(el => {
                el.classList.remove('open');
                const chevron = el.querySelector('.chevron');
                if (chevron) chevron.style.transform = 'rotate(0deg)';
            });
            if (!isOpen) {
                item.classList.add('open');
                const chevron = item.querySelector('.chevron');
                if (chevron) chevron.style.transform = 'rotate(180deg)';
            }
        });
    });
}

function renderExpenseStats(expenses) {
    const today = new Date();
    const todaySum = expenses
        .filter(e => {
            const d = new Date(e.expense_date);
            return d.toDateString() === today.toDateString();
        })
        .reduce((acc, e) => acc + Number(e.amount || 0), 0);

    const monthSum = expenses
        .filter(e => {
            const d = new Date(e.expense_date);
            return d.getFullYear() === today.getFullYear() && d.getMonth() === today.getMonth();
        })
        .reduce((acc, e) => acc + Number(e.amount || 0), 0);

    const totalSum = expenses.reduce((acc, e) => acc + Number(e.amount || 0), 0);

    // Статистика (элементы удалены из UI, но данные остаются для возможного использования)
    const expenseTodayEl = document.getElementById('expense-today');
    const expenseMonthEl = document.getElementById('expense-month');
    const expenseTotalEl = document.getElementById('expense-total');
    if (expenseTodayEl) expenseTodayEl.textContent = todaySum.toLocaleString('ru-RU') + ' сум';
    if (expenseMonthEl) expenseMonthEl.textContent = monthSum.toLocaleString('ru-RU') + ' сум';
    if (expenseTotalEl) expenseTotalEl.textContent = totalSum.toLocaleString('ru-RU') + ' сум';
}

function renderExpenseTable(expenses) {
    const tbody = document.getElementById('expense-table-body');
    if (!expenses || expenses.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" style="text-align: center; color: #95a5a6;">Нет расходов</td></tr>';
        return;
    }

    tbody.innerHTML = expenses.map(e => {
        const date = e.expense_date
            ? new Date(e.expense_date).toLocaleString('ru-RU', { timeZone: 'Asia/Tashkent' })
            : '-';
        const source = (e.expense_source === 'bank') ? 'Из р/с банка' : 'Из кассы';
        // Преобразовать Encashment обратно в Инкассация для отображения
        const displayCategory = e.category === 'Encashment' ? 'Инкассация' : e.category;
        return `
            <tr>
                <td>${date}</td>
                <td><span style="color: #e74c3c;">${displayCategory}</span></td>
                <td><strong>${Number(e.amount || 0).toLocaleString('ru-RU')} сум</strong></td>
                <td><span class="badge" style="background:#eef2ff;color:#4338ca;">${source}</span></td>
                <td>${e.employee_name ? escapeHtml(e.employee_name) : '-'}</td>
                <td>${e.description ? escapeHtml(e.description) : '-'}</td>
                <td>
                    <button class="btn-small btn-info edit-expense-btn" 
                            data-expense-id="${e.id}"
                            data-category="${escapeAttr(e.category)}"
                            data-amount="${e.amount}"
                            data-description="${escapeAttr(e.description || '')}"
                            data-source="${e.expense_source || 'cash'}"
                            data-employee-id="${e.employee_id || ''}"
                            data-salary-year="${e.salary_year || ''}"
                            data-salary-month="${e.salary_month || ''}">
                        ${financeEditIcon}
                    </button>
                    <button class="btn-small btn-danger delete-expense-btn" 
                            data-expense-id="${e.id}">
                        ${financeTrashIcon}
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

function buildExpenseMonthlyReport(expenses) {
    const monthsMap = {};
    const monthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

    (expenses || []).forEach((e) => {
        if (!e.expense_date) return;
        const d = new Date(e.expense_date);
        if (Number.isNaN(d.getTime())) return;

        const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
        if (!monthsMap[key]) {
            monthsMap[key] = {
                key,
                label: `${monthNames[d.getMonth()]} ${d.getFullYear()}`,
                total: 0,
                categories: {}
            };
        }

        const amount = Number(e.amount || 0);
        const category = e.category || 'Без категории';
        monthsMap[key].total += amount;
        monthsMap[key].categories[category] = (monthsMap[key].categories[category] || 0) + amount;
    });

    return Object.values(monthsMap).sort((a, b) => b.key.localeCompare(a.key));
}

function renderExpenseDonut(canvas, segments, total) {
    if (!canvas || !canvas.getContext) return;
    const ctx = canvas.getContext('2d');
    const size = 200;
    canvas.width = size;
    canvas.height = size;
    ctx.clearRect(0, 0, size, size);

    const center = size / 2;
    const radius = size / 2 - 8;
    const innerRadius = radius * 0.55;
    let startAngle = -Math.PI / 2;

    segments.forEach((seg) => {
        const angle = (seg.value / total) * Math.PI * 2;
        ctx.beginPath();
        ctx.arc(center, center, radius, startAngle, startAngle + angle);
        ctx.arc(center, center, innerRadius, startAngle + angle, startAngle, true);
        ctx.fillStyle = seg.color;
        ctx.fill();
        startAngle += angle;
    });

    // Inner circle for label background
    ctx.beginPath();
    ctx.arc(center, center, innerRadius - 2, 0, Math.PI * 2);
    ctx.fillStyle = 'white';
    ctx.fill();

    ctx.fillStyle = '#0f172a';
    ctx.font = '600 14px Onest, Arial, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(total.toLocaleString('ru-RU'), center, center);
}

function renderExpenseReportGrid(expenses) {
    const grid = document.getElementById('expense-report-grid');
    if (!grid) return;

    grid.innerHTML = '';
    if (!expenses || !expenses.length) {
        grid.innerHTML = '<div class="expense-report-empty">Нет данных по расходам</div>';
        return;
    }

    const months = buildExpenseMonthlyReport(expenses);
    if (!months.length) {
        grid.innerHTML = '<div class="expense-report-empty">Нет данных по расходам</div>';
        return;
    }

    months.forEach((month) => {
        const card = document.createElement('div');
        card.className = 'expense-report-card';

        const header = document.createElement('div');
        header.className = 'expense-report-header';
        header.innerHTML = `<div style="font-weight: 700;">${month.label}</div><div style="color:#64748b; font-size:13px;">${month.total.toLocaleString('ru-RU')} сум</div>`;

        const canvas = document.createElement('canvas');
        canvas.style.width = '100%';
        canvas.style.height = '200px';

        const segments = Object.entries(month.categories).map(([category, value]) => ({
            category,
            value,
            color: getExpenseCategoryColor(category)
        })).filter(seg => seg.value > 0);

        const legend = document.createElement('div');
        legend.className = 'expense-report-legend';
        legend.innerHTML = segments.map((seg) => {
            const share = month.total ? Math.round((seg.value / month.total) * 100) : 0;
            // Конвертируем Encashment -> Инкассация для отображения
            const displayCategory = seg.category === 'Encashment' ? 'Инкассация' : seg.category;
            return `<div class="expense-legend-item"><span class="expense-legend-dot" style="background:${seg.color};"></span><span>${displayCategory} — ${seg.value.toLocaleString('ru-RU')} сум (${share}%)</span></div>`;
        }).join('');

        card.appendChild(header);
        card.appendChild(canvas);
        card.appendChild(legend);
        grid.appendChild(card);

        if (segments.length && month.total > 0) {
            renderExpenseDonut(canvas, segments, month.total);
        }
    });
}

// Загрузка расходов
async function loadExpenses() {
    try {
        const response = await fetch('/api/finances/expenses');
        const data = await response.json();
        allExpenseData = data.expenses || [];
        await ensureExpenseCategoryOptions(allExpenseData.map(e => e.category));
        renderExpenseStats(allExpenseData);
        renderExpenseReportGrid(allExpenseData);
        if (!expenseDefaultFilterApplied) {
            const todayDate = new Date();
            const startOfMonth = new Date(todayDate.getFullYear(), todayDate.getMonth(), 1).toISOString().split('T')[0];
            const today = todayDate.toISOString().split('T')[0];
            const fromInput = document.getElementById('expense-date-from');
            const toInput = document.getElementById('expense-date-to');
            if (fromInput && !fromInput.value) fromInput.value = startOfMonth;
            if (toInput && !toInput.value) toInput.value = today;
            expenseDefaultFilterApplied = true;
            filterExpenses();
        } else {
            renderExpenseTable(allExpenseData);
        }
    } catch (error) {
        console.error('Ошибка загрузки расходов:', error);
    }
}

// Загрузка аналитики
async function loadAnalytics() {
    try {
        const response = await fetch('/api/finances/analytics');
        const data = await response.json();

        // Таблица
        const tbody = document.getElementById('analytics-table-body');
        if (data.months.length === 0) {
            tbody.innerHTML = '<tr><td colspan="4" style="text-align: center; color: #95a5a6;">Нет данных</td></tr>';
            return;
        }

        // Подсчёт итогов
        const totalIncome = data.months.reduce((acc, m) => acc + Number(m.income || 0), 0);
        const totalExpense = data.months.reduce((acc, m) => acc + Number(m.expense || 0), 0);
        const totalBalance = totalIncome - totalExpense;

        const rows = data.months.map(m => {
            const balance = m.income - m.expense;
            const balanceColor = balance >= 0 ? '#27ae60' : '#e74c3c';

            return `
                <tr>
                    <td><strong>${m.month_name}</strong></td>
                    <td style="color: #27ae60;">${m.income.toLocaleString('ru-RU')}</td>
                    <td style="color: #e74c3c;">${m.expense.toLocaleString('ru-RU')}</td>
                    <td style="color: ${balanceColor}; font-weight: bold;">
                        ${balance.toLocaleString('ru-RU')}
                    </td>
                </tr>
            `;
        }).join('');

        const totalRow = `
            <tr class="analytics-total-row" style="background: #f8f9fa; font-weight: bold;">
                <td>Итого</td>
                <td style="color: #27ae60;">${totalIncome.toLocaleString('ru-RU')}</td>
                <td style="color: #e74c3c;">${totalExpense.toLocaleString('ru-RU')}</td>
                <td style="color: ${totalBalance >= 0 ? '#27ae60' : '#e74c3c'};">
                    ${totalBalance.toLocaleString('ru-RU')}
                </td>
            </tr>
        `;

        tbody.innerHTML = rows + totalRow;

        // График (простая визуализация без Chart.js)
        drawSimpleChart(data.months);
    } catch (error) {
        console.error('Ошибка загрузки аналитики:', error);
    }
}

// Простой график на Canvas
function drawSimpleChart(months) {
    const canvas = document.getElementById('financeChart');
    const ctx = canvas.getContext('2d');

    canvas.width = canvas.offsetWidth;
    canvas.height = 150;

    ctx.clearRect(0, 0, canvas.width, canvas.height);

    if (months.length === 0) {
        ctx.fillStyle = '#95a5a6';
        ctx.font = '12px Onest, Arial';
        ctx.textAlign = 'center';
        ctx.fillText('Нет данных для отображения', canvas.width / 2, canvas.height / 2);
        return;
    }

    const padding = 25;
    const chartWidth = canvas.width - padding * 2;
    const chartHeight = canvas.height - padding * 2;

    const maxValueRaw = Math.max(...months.map(m => Math.max(m.income, m.expense)));
    const maxValue = maxValueRaw > 0 ? maxValueRaw : 1; // избежать деления на 0
    const barWidth = chartWidth / (months.length * 2 + 1);

    months.forEach((m, i) => {
        const x = padding + i * barWidth * 2 + barWidth / 2;

        // Приход (зелёный)
        const incomeHeight = (m.income / maxValue) * chartHeight;
        ctx.fillStyle = '#27ae60';
        ctx.fillRect(x, padding + chartHeight - incomeHeight, barWidth * 0.8, incomeHeight);

        // Расход (красный)
        const expenseHeight = (m.expense / maxValue) * chartHeight;
        ctx.fillStyle = '#e74c3c';
        ctx.fillRect(x + barWidth, padding + chartHeight - expenseHeight, barWidth * 0.8, expenseHeight);

        // Подпись месяца
        ctx.fillStyle = '#2c3e50';
        ctx.font = '9px Onest, Arial';
        ctx.textAlign = 'center';
        ctx.fillText(m.month_name, x + barWidth, canvas.height - 5);
    });

    // Легенда
    ctx.fillStyle = '#27ae60';
    ctx.fillRect(padding, 6, 12, 10);
    ctx.fillStyle = '#2c3e50';
    ctx.font = '10px Onest, Arial';
    ctx.textAlign = 'left';
    ctx.fillText('Приход', padding + 18, 14);

    ctx.fillStyle = '#e74c3c';
    ctx.fillRect(padding + 70, 6, 12, 10);
    ctx.fillText('Расход', padding + 88, 14);
}

// Загрузить группы для фильтра прихода
async function loadIncomeGroups() {
    try {
        const response = await fetch('/api/groups');
        const groups = await response.json();
        const groupSelect = document.getElementById('income-group-filter');
        if (groupSelect) {
            groupSelect.innerHTML = '<option value="">Все группы</option>' +
                groups.map(g => `<option value="${g.id}">${escapeHtml(g.name)}</option>`).join('');
            await loadGroupStudents(groupSelect.value);
        }
    } catch (error) {
        console.error('Ошибка загрузки групп:', error);
    }
}

// Загрузить учеников выбранной группы или всего клуба, если группа не выбрана
async function loadGroupStudents(groupId) {
    const studentInput = document.getElementById('income-student-filter');
    const studentsList = document.getElementById('income-students-list');

    try {
        studentInput.disabled = true;
        studentInput.placeholder = 'Загрузка учеников...';
        const groupQuery = groupId ? `&group_id=${encodeURIComponent(groupId)}` : '';
        const response = await fetch(`/api/students?view=options&active_only=1${groupQuery}`);
        const students = await response.json();
        if (!response.ok || !Array.isArray(students)) {
            throw new Error('Не удалось загрузить учеников');
        }
        const availableStudents = students.filter(s => (
            s.status === 'active' && (!groupId || String(s.group_id || '') === String(groupId))
        ));

        studentsList.innerHTML = availableStudents.map(s =>
            `<option value="${escapeAttr(s.full_name)}">${escapeHtml(s.full_name)}${s.group_name ? ` · ${escapeHtml(s.group_name)}` : ''}${s.student_number ? ` · №${escapeHtml(s.student_number)}` : ''}</option>`
        ).join('');

        studentInput.disabled = false;
        studentInput.placeholder = groupId ? 'Введите ФИО ученика...' : 'Введите ФИО — группа не обязательна';
    } catch (error) {
        console.error('Ошибка загрузки учеников:', error);
        studentInput.disabled = true;
        studentInput.placeholder = 'Ошибка загрузки...';
    }
}

// Обработчик изменения группы
document.addEventListener('DOMContentLoaded', () => {
    const groupFilter = document.getElementById('income-group-filter');
    if (groupFilter) {
        groupFilter.addEventListener('change', (e) => {
            loadGroupStudents(e.target.value);
            // Сбросить выбор ученика при смене группы
            document.getElementById('income-student-filter').value = '';
        });
    }
});

// ==================== FILTER TOGGLE FUNCTIONALITY ====================

// Переключение фильтра для прихода
function toggleIncomeFilter() {
    // Проверка на мобильное устройство
    if (window.innerWidth <= 768) {
        if (window.openFilterModal) {
            window.openFilterModal('incomeFilterPanel', 'Фильтры прихода');
        }
        return;
    }

    const filterPanel = document.getElementById('incomeFilterPanel');
    const filterToggleBtn = document.getElementById('incomeFilterToggleBtn');
    const filterToggleText = document.getElementById('incomeFilterToggleText');

    if (filterPanel && filterToggleBtn && filterToggleText) {
        if (filterPanel.style.display === 'none') {
            filterPanel.style.display = 'block';
            filterToggleText.textContent = 'Скрыть фильтр';
            filterToggleBtn.classList.add('active');
        } else {
            filterPanel.style.display = 'none';
            filterToggleText.textContent = 'Фильтр';
            filterToggleBtn.classList.remove('active');
        }
    }
}

// Переключение фильтра для расходов
function toggleExpenseFilter() {
    // Проверка на мобильное устройство
    if (window.innerWidth <= 768) {
        if (window.openFilterModal) {
            window.openFilterModal('expenseFilterPanel', 'Фильтры расходов');
        }
        return;
    }

    const filterPanel = document.getElementById('expenseFilterPanel');
    const filterToggleBtn = document.getElementById('expenseFilterToggleBtn');
    const filterToggleText = document.getElementById('expenseFilterToggleText');

    if (filterPanel && filterToggleBtn && filterToggleText) {
        if (filterPanel.style.display === 'none') {
            filterPanel.style.display = 'block';
            filterToggleText.textContent = 'Скрыть фильтр';
            filterToggleBtn.classList.add('active');
        } else {
            filterPanel.style.display = 'none';
            filterToggleText.textContent = 'Фильтр';
            filterToggleBtn.classList.remove('active');
        }
    }
}

// Инициализация кнопок фильтров
document.addEventListener('DOMContentLoaded', () => {
    const incomeFilterToggleBtn = document.getElementById('incomeFilterToggleBtn');
    if (incomeFilterToggleBtn) {
        incomeFilterToggleBtn.addEventListener('click', toggleIncomeFilter);
    }

    const expenseFilterToggleBtn = document.getElementById('expenseFilterToggleBtn');
    if (expenseFilterToggleBtn) {
        expenseFilterToggleBtn.addEventListener('click', toggleExpenseFilter);
    }
});

// Загрузить все данные при открытии страницы
loadIncomeGroups();
loadIncome();
loadDebtors();
ensureExpenseCategoryOptions();
loadExpenses();

// ==================== ADD INCOME MODAL ====================
const addIncomeModal = document.getElementById('addIncomeModal');
const addIncomeBtn = document.getElementById('addIncomeBtn');
const addIncomeForm = document.getElementById('addIncomeForm');

function confirmCloseAddIncomeModal() {
    const shouldClose = confirm('Закрыть окно? Несохраненные данные будут потеряны.');
    if (!shouldClose) return;
    if (typeof resetIncomeForm === 'function') resetIncomeForm();
    if (addIncomeModal) addIncomeModal.style.display = 'none';
}

let allStudentsData = {}; // Хранилище данных учеников для доступа к фото
let financeEmployees = [];

function escapeHtml(value) {
    return String(value ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

function escapeAttr(value) {
    return escapeHtml(value).replace(/`/g, '&#096;');
}

async function loadFinanceEmployees() {
    if (financeEmployees.length) return financeEmployees;
    try {
        const response = await fetch('/api/finances/employees');
        const data = await response.json();
        financeEmployees = Array.isArray(data.employees) ? data.employees : [];
    } catch (error) {
        console.error('Ошибка загрузки сотрудников:', error);
        financeEmployees = [];
    }
    return financeEmployees;
}

function populateExpenseEmployeeSelect(selectId, selectedId = '') {
    const select = document.getElementById(selectId);
    if (!select) return;

    select.innerHTML = '<option value="">Выберите сотрудника</option>';
    financeEmployees.forEach((employee) => {
        const option = document.createElement('option');
        option.value = String(employee.id);
        option.textContent = employee.role ? `${employee.name} · ${employee.role}` : employee.name;
        select.appendChild(option);
    });

    if (selectedId) {
        select.value = String(selectedId);
    }
    setupSearchableSelect(selectId, 'Поиск по ФИО...');
}

function populateSalaryPeriod(prefix, selectedYear = null, selectedMonth = null) {
    const monthSelect = document.getElementById(`${prefix}-salary-month`);
    const yearSelect = document.getElementById(`${prefix}-salary-year`);
    if (!monthSelect || !yearSelect) return;

    const monthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь', 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];
    const now = new Date();
    const currentYear = selectedYear || now.getFullYear();
    const currentMonth = selectedMonth || (now.getMonth() + 1);

    monthSelect.innerHTML = monthNames.map((name, index) => `<option value="${index + 1}">${name}</option>`).join('');
    yearSelect.innerHTML = '';
    for (let year = now.getFullYear() - 2; year <= now.getFullYear() + 1; year += 1) {
        yearSelect.insertAdjacentHTML('beforeend', `<option value="${year}">${year}</option>`);
    }
    monthSelect.value = String(currentMonth);
    yearSelect.value = String(currentYear);
}

function toggleSalaryEmployeeField(categorySelectId, groupId, selectId, periodGroupId = '', periodPrefix = '') {
    const categorySelect = document.getElementById(categorySelectId);
    const group = document.getElementById(groupId);
    const employeeSelect = document.getElementById(selectId);
    if (!categorySelect || !group || !employeeSelect) return;

    const isSalary = categorySelect.value === 'Зарплата';
    const periodGroup = periodGroupId ? document.getElementById(periodGroupId) : null;
    group.style.display = isSalary ? 'block' : 'none';
    if (periodGroup) periodGroup.style.display = isSalary ? 'block' : 'none';
    if (isSalary) {
        employeeSelect.setAttribute('required', 'required');
        setupSearchableSelect(selectId, 'Поиск по ФИО...');
        if (periodPrefix) {
            const monthSelect = document.getElementById(`${periodPrefix}-salary-month`);
            const yearSelect = document.getElementById(`${periodPrefix}-salary-year`);
            if (!monthSelect?.value || !yearSelect?.value) {
                populateSalaryPeriod(periodPrefix);
            }
        }
    } else {
        employeeSelect.value = '';
        employeeSelect.removeAttribute('required');
        setupSearchableSelect(selectId, 'Поиск по ФИО...');
    }
}

function setupSearchableSelect(selectId, placeholder = 'Поиск...') {
    const select = document.getElementById(selectId);
    const wrapper = document.querySelector(`[data-searchable-select="${selectId}"]`);
    if (!select || !wrapper) return;

    const input = wrapper.querySelector('.searchable-select-input');
    const optionsBox = wrapper.querySelector('.searchable-select-options');
    if (!input || !optionsBox) return;

    input.placeholder = placeholder;

    const getOptions = () => Array.from(select.options).filter(option => option.value);

    const positionOptions = () => {
        if (!wrapper.classList.contains('open')) return;
        const rect = input.getBoundingClientRect();
        const gap = 8;
        const minHeight = 120;
        const preferredHeight = 260;
        const spaceBelow = window.innerHeight - rect.bottom - gap;
        const spaceAbove = rect.top - gap;
        const openAbove = spaceBelow < minHeight && spaceAbove > spaceBelow;
        const availableHeight = Math.max(minHeight, Math.min(preferredHeight, (openAbove ? spaceAbove : spaceBelow) - gap));

        optionsBox.style.left = `${rect.left}px`;
        optionsBox.style.width = `${rect.width}px`;
        optionsBox.style.maxHeight = `${availableHeight}px`;
        if (openAbove) {
            optionsBox.style.top = 'auto';
            optionsBox.style.bottom = `${window.innerHeight - rect.top + gap}px`;
        } else {
            optionsBox.style.top = `${rect.bottom + gap}px`;
            optionsBox.style.bottom = 'auto';
        }
    };

    const syncInput = () => {
        const selected = select.selectedOptions && select.selectedOptions[0];
        input.disabled = select.disabled;
        input.value = selected && selected.value ? selected.textContent.trim() : '';
    };

    const close = () => wrapper.classList.remove('open');
    const open = () => {
        renderOptions(input.value);
        wrapper.classList.add('open');
        requestAnimationFrame(positionOptions);
    };

    const renderOptions = (query = '') => {
        const normalizedQuery = query.trim().toLowerCase();
        const options = getOptions().filter(option =>
            option.textContent.toLowerCase().includes(normalizedQuery)
        );

        if (!options.length) {
            optionsBox.innerHTML = '<div class="searchable-select-empty">Ничего не найдено</div>';
            return;
        }

        optionsBox.innerHTML = options.map(option => `
            <div class="searchable-select-option ${option.value === select.value ? 'is-selected' : ''}"
                data-value="${escapeHtml(option.value)}">
                ${escapeHtml(option.textContent.trim())}
            </div>
        `).join('');

        optionsBox.querySelectorAll('.searchable-select-option').forEach(optionEl => {
            optionEl.addEventListener('mousedown', (event) => {
                event.preventDefault();
                select.value = optionEl.dataset.value;
                syncInput();
                close();
                select.dispatchEvent(new Event('change', { bubbles: true }));
            });
        });
        requestAnimationFrame(positionOptions);
    };

    if (!wrapper.dataset.searchReady) {
        wrapper.dataset.searchReady = 'true';
        input.addEventListener('focus', () => {
            input.select();
            renderOptions('');
            wrapper.classList.add('open');
            requestAnimationFrame(positionOptions);
        });
        input.addEventListener('input', () => open());
        input.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                close();
                syncInput();
            }
        });
        input.addEventListener('blur', () => {
            setTimeout(() => {
                close();
                syncInput();
            }, 120);
        });
        select.addEventListener('change', syncInput);
        window.addEventListener('resize', positionOptions);
        window.addEventListener('scroll', positionOptions, true);
    }

    syncInput();
    renderOptions();
}

// Скрыть зависимые поля, оставив общий выбор ученика по всему клубу
function resetIncomeForm() {
    const studentSelectGroup = document.getElementById('student-select-group');
    const yearMonthSelectGroup = document.getElementById('year-month-select-group');
    const dateSelectGroup = document.getElementById('date-select-group');
    const paymentMethodGroup = document.getElementById('payment-method-group');
    const incomePaymentAmountGroup = document.getElementById('income-payment-amount-group');
    const notesInputGroup = document.getElementById('notes-input-group');

    if (studentSelectGroup) studentSelectGroup.style.display = 'block';
    if (yearMonthSelectGroup) yearMonthSelectGroup.style.display = 'none';
    if (dateSelectGroup) dateSelectGroup.style.display = 'none';
    if (paymentMethodGroup) paymentMethodGroup.style.display = 'none';
    if (incomePaymentAmountGroup) incomePaymentAmountGroup.style.display = 'none';
    if (notesInputGroup) notesInputGroup.style.display = 'none';

    document.getElementById('add-income-student').value = '';
    setupSearchableSelect('add-income-student', 'Поиск по ФИО...');
    document.getElementById('add-income-year').value = '';
    document.getElementById('add-income-month').value = '';
    document.getElementById('add-income-amount').value = '';
    document.getElementById('add-income-payment-type').value = 'cash';
    document.getElementById('add-income-notes').value = '';

    // Сбросить кнопки типа оплаты и активировать "Наличные"
    document.querySelectorAll('.finances-payment-type-btn').forEach(btn => {
        btn.classList.remove('active');
        const border = '2px solid var(--theme-input-border)';
        const bg = 'var(--theme-input-bg)';
        const color = 'var(--theme-text-primary)';
        btn.style.border = border;
        btn.style.background = bg;
        btn.style.color = color;
    });

    // Активировать кнопку "Наличные"
    const cashBtn = document.querySelector('.finances-payment-type-btn[data-payment-type="cash"]');
    if (cashBtn) {
        cashBtn.classList.add('active');
        cashBtn.style.border = '2px solid #ff8a00';
        cashBtn.style.background = 'linear-gradient(135deg, rgba(255, 138, 0, 0.1) 0%, rgba(217, 111, 0, 0.1) 100%)';
        cashBtn.style.color = '#ff8a00';
    }

    document.getElementById('student-photo-container').style.display = 'none';
    document.getElementById('student-photo-img').style.display = 'none';
    document.getElementById('student-photo-placeholder').style.display = 'flex';
    const maxAmountElement = document.getElementById('add-income-max-amount');
    if (maxAmountElement) {
        maxAmountElement.style.display = 'none';
    }
    document.getElementById('month-debt-info').style.display = 'none';

    updatePaymentQrDisplay('cash');

    // Установить дату оплаты по умолчанию на сегодня
    const today = new Date().toISOString().split('T')[0];
    document.getElementById('add-income-date').value = today;
}

let paymentMethodSettings = {
    __loaded: false,
    click: { enabled: false, qrUrl: '' },
    payme: { enabled: false, qrUrl: '' },
    uzum: { enabled: false, qrUrl: '' },
    card: { enabled: true, qrUrl: '' },
    humo: { enabled: false, qrUrl: '' },
    paynet: { enabled: false, qrUrl: '' },
    multicard: { enabled: false, qrUrl: '' },
    oson: { enabled: false, qrUrl: '' },
    transfer: { enabled: false, qrUrl: '' }
};

async function loadPaymentMethodSettings() {
    if (paymentMethodSettings.__loaded) return paymentMethodSettings;
    try {
        const resp = await fetch('/api/club-settings');
        const data = await resp.json();
        paymentMethodSettings = {
            __loaded: true,
            click: {
                enabled: !!data.payment_click_enabled,
                qrUrl: data.payment_click_qr_url || ''
            },
            payme: {
                enabled: !!data.payment_payme_enabled,
                qrUrl: data.payment_payme_qr_url || ''
            },
            uzum: {
                enabled: !!data.payment_uzum_enabled,
                qrUrl: data.payment_uzum_qr_url || ''
            },
            card: {
                enabled: !!data.payment_uzcard_enabled,
                qrUrl: ''
            },
            humo: {
                enabled: !!data.payment_humo_enabled,
                qrUrl: ''
            },
            paynet: {
                enabled: !!data.payment_paynet_enabled,
                qrUrl: data.payment_paynet_qr_url || ''
            },
            multicard: {
                enabled: !!data.payment_multicard_enabled,
                qrUrl: data.payment_multicard_qr_url || ''
            },
            oson: {
                enabled: !!data.payment_oson_enabled,
                qrUrl: data.payment_oson_qr_url || ''
            },
            transfer: {
                enabled: !!data.payment_transfer_enabled,
                qrUrl: ''
            }
        };
    } catch (error) {
        console.error('Ошибка загрузки способов оплаты:', error);
        paymentMethodSettings.__loaded = true;
    }
    return paymentMethodSettings;
}

function applyPaymentMethodSettings() {
    const mapping = {
        click: paymentMethodSettings.click,
        payme: paymentMethodSettings.payme,
        uzum: paymentMethodSettings.uzum,
        card: paymentMethodSettings.card,
        humo: paymentMethodSettings.humo,
        paynet: paymentMethodSettings.paynet,
        multicard: paymentMethodSettings.multicard,
        oson: paymentMethodSettings.oson,
        transfer: paymentMethodSettings.transfer
    };

    Object.keys(mapping).forEach((key) => {
        const btn = document.querySelector(`.finances-payment-type-btn[data-payment-type="${key}"]`);
        if (btn) {
            btn.style.display = mapping[key].enabled ? 'inline-flex' : 'none';
        }
    });

    const activeBtn = document.querySelector('.finances-payment-type-btn.active');
    if (activeBtn && activeBtn.style.display === 'none') {
        const cashBtn = document.querySelector('.finances-payment-type-btn[data-payment-type="cash"]');
        if (cashBtn) {
            cashBtn.click();
        }
    }
}

function resolveQrImageSrc(rawValue) {
    const value = (rawValue || '').trim();
    if (!value) return '';

    const lower = value.toLowerCase();
    const looksLikeImage = lower.startsWith('data:image') || /\.(png|jpg|jpeg|gif|svg|webp)(\?|$)/i.test(lower);
    if (looksLikeImage) return value;

    const encoded = encodeURIComponent(value);
    return `https://api.qrserver.com/v1/create-qr-code/?size=300x300&data=${encoded}`;
}

function getPaymentDisplayName(paymentType) {
    const mapping = {
        cash: 'Наличные',
        card: 'UZCARD',
        humo: 'HUMO',
        paynet: 'Paynet',
        multicard: 'Multicard',
        oson: 'Oson',
        click: 'Click',
        payme: 'Payme',
        uzum: 'Uzum',
        transfer: 'Перечисление'
    };
    return mapping[paymentType] || paymentType.charAt(0).toUpperCase() + paymentType.slice(1);
}

function updatePaymentQrDisplay(paymentType) {
    const qrBox = document.getElementById('paymentQrBox');
    const qrImage = document.getElementById('paymentQrImage');
    const qrTitle = document.getElementById('paymentQrTitle');
    const qrHint = document.getElementById('paymentQrHint');

    if (!qrBox || !qrImage || !qrTitle || !qrHint) return;

    const config = paymentMethodSettings[paymentType];
    const qrSrc = resolveQrImageSrc(config?.qrUrl);
    if (!config || !config.enabled || !qrSrc) {
        qrBox.style.display = 'none';
        qrImage.src = '';
        return;
    }

    qrTitle.textContent = `QR для ${getPaymentDisplayName(paymentType)}`;
    qrHint.textContent = 'Отсканируйте QR-код для оплаты';
    qrImage.src = qrSrc;
    qrBox.style.display = 'flex';
}

// Форматирование суммы с разделителями тысяч
function sanitizeAmountValue(value) {
    const cleaned = (value || '').toString().replace(/[^0-9.,-]/g, '').replace(',', '.');
    const parsed = parseFloat(cleaned);
    return isNaN(parsed) ? 0 : parsed;
}

function formatAmountInputValue(inputEl) {
    if (!inputEl) return;
    const digits = (inputEl.value || '').replace(/[^0-9]/g, '');
    if (!digits) {
        inputEl.value = '';
        return;
    }
    const num = parseInt(digits, 10);
    inputEl.value = num.toLocaleString('ru-RU');
}

function attachAmountFormatting(inputId) {
    const el = document.getElementById(inputId);
    if (!el) return;

    el.addEventListener('focus', () => {
        el.value = (el.value || '').replace(/[^0-9]/g, '');
    });

    const formatHandler = () => formatAmountInputValue(el);
    el.addEventListener('input', formatHandler);
    el.addEventListener('blur', formatHandler);
}

// Загрузить всех активных учеников клуба в единый список оплаты
async function loadIncomeModalStudents() {
    const studentSelect = document.getElementById('add-income-student');

    try {
        const response = await fetch('/api/students?view=options&active_only=1');
        const students = await response.json();
        const activeStudents = students.filter(s => s.status === 'active');

        // Сохранить данные учеников для доступа к фото
        allStudentsData = {};
        activeStudents.forEach(s => {
            allStudentsData[s.id] = s;
        });

        studentSelect.innerHTML = '<option value="">Выберите ученика</option>' +
            activeStudents.map(s => {
                const groupName = s.group_name || 'Без группы';
                const studentNumber = s.student_number ? ` · №${s.student_number}` : '';
                return `<option value="${s.id}" data-photo="${s.photo_path || ''}">${escapeHtml(s.full_name)} · ${escapeHtml(groupName)}${escapeHtml(studentNumber)}</option>`;
            }).join('');

        setupSearchableSelect('add-income-student', 'Поиск по ФИО...');
        document.getElementById('student-select-group').style.display = 'block';
    } catch (error) {
        console.error('Ошибка загрузки учеников:', error);
        studentSelect.innerHTML = '<option value="">Не удалось загрузить учеников</option>';
        setupSearchableSelect('add-income-student', 'Поиск по ФИО...');
    }
}

// Отобразить фото ученика
function displayStudentPhoto(studentId) {
    const student = allStudentsData[studentId];
    const photoContainer = document.getElementById('student-photo-container');
    const photoImg = document.getElementById('student-photo-img');
    const photoPlaceholder = document.getElementById('student-photo-placeholder');

    if (student && student.photo_path) {
        const photoPath = student.photo_path.replace('frontend/static/', '').replace(/\\/g, '/');
        photoImg.src = `/static/${photoPath}`;
        photoImg.style.display = 'block';
        photoPlaceholder.style.display = 'none';
        photoContainer.style.display = 'flex';
    } else {
        photoImg.style.display = 'none';
        photoPlaceholder.style.display = 'flex';
        photoContainer.style.display = 'flex';
    }
}

// Загрузить доступные годы и месяцы для ученика
async function loadAvailableMonths(studentId) {
    if (!studentId) {
        document.getElementById('year-month-select-group').style.display = 'none';
        return;
    }

    try {
        const response = await fetch(`/api/students/${studentId}/monthly-payments`);
        const data = await response.json();
        const paymentsByMonth = data.payments_by_month || {};
        const tariffPrice = data.tariff_price || 0;

        const currentDate = new Date();
        const currentYear = currentDate.getFullYear();
        const currentMonth = currentDate.getMonth() + 1;

        // Получить дату поступления ученика
        const student = allStudentsData[studentId];
        let admissionDate = null;
        let admissionYear = null;
        let admissionMonth = null;

        if (student && student.admission_date) {
            admissionDate = new Date(student.admission_date);
            admissionYear = admissionDate.getFullYear();
            admissionMonth = admissionDate.getMonth() + 1;
        }

        // Инициализация года - только текущий год
        const yearSelect = document.getElementById('add-income-year');
        yearSelect.innerHTML = '<option value="">Выберите год</option>';

        // Только текущий год
        yearSelect.innerHTML += `<option value="${currentYear}" selected>${currentYear}</option>`;

        document.getElementById('year-month-select-group').style.display = 'block';

        // Сохранить данные для использования при выборе месяца
        window.currentStudentPaymentData = {
            paymentsByMonth,
            tariffPrice,
            currentYear,
            currentMonth,
            admissionYear,
            admissionMonth
        };

        // Автоматически загрузить месяцы для текущего года
        setTimeout(() => {
            loadAvailableMonthsForYear(currentYear);
        }, 100);
    } catch (error) {
        console.error('Ошибка загрузки информации об оплате:', error);
        document.getElementById('year-month-select-group').style.display = 'none';
    }
}

// Загрузить доступные месяцы для выбранного года
function loadAvailableMonthsForYear(year) {
    if (!year || !window.currentStudentPaymentData) {
        return;
    }

    const { paymentsByMonth, tariffPrice, currentYear, currentMonth, admissionYear, admissionMonth } = window.currentStudentPaymentData;
    const monthSelect = document.getElementById('add-income-month');
    const monthNames = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
        'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'];

    monthSelect.innerHTML = '<option value="">Выберите месяц</option>';

    const selectedYear = parseInt(year);
    const maxMonth = (selectedYear === currentYear) ? currentMonth : 12;

    // Определить минимальный месяц с учетом даты поступления
    let minMonth = 1;
    if (admissionYear !== null && admissionMonth !== null) {
        // Если ученик поступил в выбранном году, начинаем с месяца поступления
        if (selectedYear === admissionYear) {
            minMonth = admissionMonth;
        }
        // Если ученик поступил позже выбранного года, не показываем месяцы
        else if (selectedYear < admissionYear) {
            document.getElementById('month-select-group').style.display = 'none';
            alert('Ученик поступил позже выбранного года');
            return;
        }
        // Если выбранный год позже года поступления, показываем все месяцы с начала года
    }

    for (let month = minMonth; month <= maxMonth; month++) {
        const monthKey = `${selectedYear}-${String(month).padStart(2, '0')}`;
        const monthData = paymentsByMonth[monthKey];
        const paidAmount = monthData ? monthData.total_paid : 0;
        const remainder = tariffPrice - paidAmount;

        // Пропускаем полностью оплаченные месяцы
        if (remainder <= 0) {
            continue;
        }

        const option = document.createElement('option');
        option.value = month;
        option.textContent = monthNames[month - 1];
        option.dataset.remainder = remainder;
        option.dataset.paid = paidAmount;
        monthSelect.appendChild(option);
    }

    if (monthSelect.options.length <= 1) {
        alert('Нет доступных месяцев для оплаты');
    }
}

// Обновить информацию о долге при выборе месяца
function updateMonthDebtInfo() {
    const monthSelect = document.getElementById('add-income-month');
    const selectedOption = monthSelect.options[monthSelect.selectedIndex];
    const debtInfo = document.getElementById('month-debt-info');

    if (selectedOption && selectedOption.value) {
        const remainder = parseFloat(selectedOption.dataset.remainder || 0);
        const paid = parseFloat(selectedOption.dataset.paid || 0);
        const tariffPrice = window.currentStudentPaymentData?.tariffPrice || 0;

        if (remainder > 0) {
            debtInfo.style.display = 'block';
            debtInfo.style.color = '#ff8a00';
            debtInfo.textContent = `Долг: ${remainder.toLocaleString('ru-RU')} сум (Оплачено: ${paid.toLocaleString('ru-RU')} / Тариф: ${tariffPrice.toLocaleString('ru-RU')} сум)`;

            // Показать поля для даты, способа оплаты и суммы
            document.getElementById('date-select-group').style.display = 'block';
            document.getElementById('payment-method-group').style.display = 'block';
            document.getElementById('income-payment-amount-group').style.display = 'block';
            document.getElementById('notes-input-group').style.display = 'block';

            // Обновить максимальную сумму для поля суммы
            const amountInput = document.getElementById('add-income-amount');
            if (amountInput) {
                amountInput.setAttribute('max', remainder);
            }

            const maxAmountElement = document.getElementById('add-income-max-amount');
            if (maxAmountElement) {
                maxAmountElement.style.display = 'block';
                maxAmountElement.textContent = `Максимальная сумма: ${remainder.toLocaleString('ru-RU')} сум`;
            }
        }
    } else {
        debtInfo.style.display = 'none';
        document.getElementById('date-select-group').style.display = 'none';
        document.getElementById('payment-method-group').style.display = 'none';
        document.getElementById('income-payment-amount-group').style.display = 'none';
        document.getElementById('notes-input-group').style.display = 'none';
    }
}

// Инициализация ограничения даты оплаты
function initPaymentDateLimits() {
    const dateInput = document.getElementById('add-income-date');
    const today = new Date();
    const maxDate = today.toISOString().split('T')[0];

    const minDate = new Date(today);
    minDate.setDate(minDate.getDate() - 14);
    const minDateStr = minDate.toISOString().split('T')[0];

    dateInput.setAttribute('max', maxDate);
    dateInput.setAttribute('min', minDateStr);
    // Значение по умолчанию устанавливается в resetIncomeForm()
}

// Открыть модальное окно добавления прихода
if (addIncomeBtn) {
    addIncomeBtn.addEventListener('click', async () => {
        addIncomeModal.style.display = 'block';
        addIncomeForm.reset();
        resetIncomeForm();
        await loadIncomeModalStudents();
        initPaymentDateLimits();
        await loadPaymentMethodSettings();
        applyPaymentMethodSettings();
        updatePaymentQrDisplay(document.getElementById('add-income-payment-type').value || 'cash');
    });
}

// Обработчик изменения группы
document.addEventListener('DOMContentLoaded', () => {
    // Обработчик изменения ученика
    const studentSelect = document.getElementById('add-income-student');
    if (studentSelect) {
        studentSelect.addEventListener('change', (e) => {
            const studentId = e.target.value;
            if (studentId) {
                displayStudentPhoto(parseInt(studentId));
                loadAvailableMonths(parseInt(studentId));
            } else {
                document.getElementById('year-month-select-group').style.display = 'none';
                document.getElementById('student-photo-container').style.display = 'none';
            }
        });
    }

    // Обработчик изменения года
    const yearSelect = document.getElementById('add-income-year');
    if (yearSelect) {
        yearSelect.addEventListener('change', (e) => {
            if (e.target.value) {
                loadAvailableMonthsForYear(parseInt(e.target.value));
            }
        });
    }

    // Обработчик изменения месяца
    const monthSelect = document.getElementById('add-income-month');
    if (monthSelect) {
        monthSelect.addEventListener('change', () => {
            updateMonthDebtInfo();
        });
    }

    attachAmountFormatting('add-income-amount');
    attachAmountFormatting('edit-payment-amount');
});

// Окно оплаты закрывается только явной кнопкой, чтобы не потерять введенные данные.

// Делегирование гарантирует выбор способа оплаты независимо от момента открытия окна.
document.addEventListener('click', (event) => {
    const button = event.target.closest('.finances-payment-type-btn');
    if (!button || !button.closest('#addIncomeModal')) return;

    event.preventDefault();
    const paymentType = button.dataset.paymentType;
    if (!paymentType) return;

    document.querySelectorAll('#addIncomeModal .finances-payment-type-btn').forEach((item) => {
        item.classList.toggle('active', item === button);
    });

    const paymentTypeInput = document.getElementById('add-income-payment-type');
    if (paymentTypeInput) paymentTypeInput.value = paymentType;
    updatePaymentQrDisplay(paymentType);
});

// Отправить форму добавления прихода
if (addIncomeForm) {
    addIncomeForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const stayOpen = e.submitter && e.submitter.id === 'add-income-save-plus';
        const studentId = document.getElementById('add-income-student').value;
        const month = document.getElementById('add-income-month').value;
        const year = document.getElementById('add-income-year').value;
        const paymentDate = document.getElementById('add-income-date').value;
        const notes = document.getElementById('add-income-notes').value || '';

        // Получить тип оплаты и сумму
        const paymentType = document.getElementById('add-income-payment-type').value;
        const amount = sanitizeAmountValue(document.getElementById('add-income-amount').value);

        if (!studentId || !month || !year || !paymentDate) {
            alert('Заполните все обязательные поля');
            return;
        }

        if (!amount || amount <= 0) {
            alert('Введите корректную сумму оплаты');
            return;
        }

        if (!paymentType) {
            alert('Выберите тип оплаты');
            return;
        }

        // Проверка максимальной суммы
        const maxAmount = parseFloat(document.getElementById('add-income-amount').getAttribute('max'));
        if (maxAmount !== null && !isNaN(maxAmount) && amount > maxAmount) {
            alert(`Сумма превышает остаток по тарифу. Доступно не более ${maxAmount.toLocaleString('ru-RU')} сум`);
            return;
        }

        // Проверка даты
        const today = new Date();
        const selectedDate = new Date(paymentDate);
        const minDate = new Date(today);
        minDate.setDate(minDate.getDate() - 14);

        if (selectedDate > today) {
            alert('Нельзя выбрать будущую дату');
            return;
        }

        if (selectedDate < minDate) {
            alert('Дата оплаты не может быть раньше чем 14 дней назад');
            return;
        }

        try {
            const response = await fetch('/api/students/add-monthly-payment', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    student_id: parseInt(studentId),
                    month: parseInt(month),
                    year: parseInt(year),
                    payment_date: paymentDate,
                    amount: amount,
                    payment_type: paymentType,
                    notes: notes
                })
            });

            const result = await response.json();

            if (response.ok && result.success) {
                // Перезагрузить данные прихода
                await loadIncome();
                await loadDebtors();

                if (stayOpen) {
                    alert('Оплата успешно добавлена!');
                    resetIncomeForm();
                    await loadIncomeModalStudents();
                    addIncomeModal.style.display = 'block';
                } else {
                    addIncomeModal.style.display = 'none';
                    resetIncomeForm();
                    alert('Оплата успешно добавлена!');
                }
            } else {
                alert('Ошибка: ' + (result.message || 'Не удалось добавить оплату'));
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Ошибка при добавлении оплаты');
        }
    });
}

// ==================== FILTER FUNCTIONS ====================

function formatLocalDateInput(dateObj) {
    const y = dateObj.getFullYear();
    const m = String(dateObj.getMonth() + 1).padStart(2, '0');
    const d = String(dateObj.getDate()).padStart(2, '0');
    return `${y}-${m}-${d}`;
}

function applyDatePreset(prefix) {
    const select = document.getElementById(`${prefix}-date-preset`);
    if (!select) return;
    const preset = select.value;
    if (!preset) return;

    const today = new Date();
    const target = new Date(today.getFullYear(), today.getMonth(), today.getDate());
    if (preset === 'yesterday') target.setDate(target.getDate() - 1);
    if (preset === 'day-before') target.setDate(target.getDate() - 2);

    const dateStr = formatLocalDateInput(target);
    const fromInput = document.getElementById(`${prefix}-date-from`);
    const toInput = document.getElementById(`${prefix}-date-to`);
    if (fromInput) fromInput.value = dateStr;
    if (toInput) toInput.value = dateStr;
}

// Функция фильтрации прихода
async function filterIncome(useCached = false) {
    const dateFrom = document.getElementById('income-date-from').value;
    const dateTo = document.getElementById('income-date-to').value;
    const studentFilter = document.getElementById('income-student-filter').value.toLowerCase();
    const groupFilter = document.getElementById('income-group-filter').value;

    try {
        if (!useCached || !allIncomeData || allIncomeData.length === 0) {
            const response = await fetch('/api/finances/income');
            const data = await response.json();
            allIncomeData = data.payments || [];
        }

        let filtered = allIncomeData.filter(p => {
            const paymentDate = new Date(p.payment_date);
            const matchDate = (!dateFrom || paymentDate >= new Date(dateFrom)) &&
                (!dateTo || paymentDate <= new Date(dateTo));
            const matchStudent = !studentFilter || (p.student_name || '').toLowerCase().includes(studentFilter);
            const matchGroup = !groupFilter || String(p.group_id || '') === String(groupFilter);

            return matchDate && matchStudent && matchGroup;
        });

        renderIncomeTable(filtered);

        // Баланс не зависит от фильтров, чтобы не показывать ноль при сужении диапазона
        updateCumulativeBalance();
    } catch (error) {
        console.error('Ошибка фильтрации прихода:', error);
    }
}

// Функция сброса фильтров прихода
function resetIncomeFilters() {
    document.getElementById('income-date-from').value = '';
    document.getElementById('income-date-to').value = '';
    const groupSelect = document.getElementById('income-group-filter');
    if (groupSelect) {
        groupSelect.value = '';
        loadGroupStudents(''); // Сбросить список учеников
    }
    const studentInput = document.getElementById('income-student-filter');
    if (studentInput) {
        studentInput.value = '';
    }
    loadIncome();
    // Сбросить баланс к полным данным
    updateCumulativeBalance();
}

// Рендер таблицы прихода
function renderIncomeTable(payments) {
    const tbody = document.getElementById('income-table-body');
    if (payments.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" style="text-align: center; color: #95a5a6;">Нет данных</td></tr>';
        return;
    }

    // Маппинг типов оплаты на русские названия
    const paymentTypeMap = {
        'cash': 'Наличные',
        'card': 'UZCARD',
        'humo': 'HUMO',
        'click': 'Click',
        'payme': 'Payme',
        'uzum': 'Uzum',
        'paynet': 'Paynet',
        'multicard': 'Multicard',
        'oson': 'Oson'
    };

    tbody.innerHTML = payments.map(p => {
        const date = new Date(p.payment_date).toLocaleDateString('ru-RU');
        const createdAt = p.created_at
            ? new Date(p.created_at).toLocaleString('ru-RU', { timeZone: 'Asia/Tashkent' })
            : 'Нет данных';
        const paymentType = paymentTypeMap[p.payment_type] || p.payment_type || 'Наличные';

        return `
            <tr>
                <td>${date}</td>
                <td>${createdAt}</td>
                <td>${escapeHtml(p.student_name)}</td>
                <td>${escapeHtml(p.group_name || '-')}</td>
                <td>${escapeHtml(p.tariff_name || '-')}</td>
                <td><strong>${p.amount_paid.toLocaleString('ru-RU')} сум</strong></td>
                <td>${escapeHtml(paymentType)}</td>
                <td>${escapeHtml(p.notes || '-')}</td>
                <td>
                    <button class="btn-small btn-info edit-income-btn" 
                            data-payment-id="${p.id}"
                            data-student-id="${p.student_id || ''}"
                            data-amount="${p.amount_paid}"
                            data-notes="${escapeAttr(p.notes || '')}">
                        ${financeEditIcon}
                    </button>
                    <button class="btn-small btn-danger delete-income-btn" 
                            data-payment-id="${p.id}">
                        ${financeTrashIcon}
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

// Функция фильтрации расходов
async function filterExpenses() {
    const dateFrom = document.getElementById('expense-date-from').value;
    const dateTo = document.getElementById('expense-date-to').value;
    const category = document.getElementById('expense-category-filter').value;

    const toLocalDate = (val) => {
        // Normalize to local midnight to avoid timezone shifts
        const d = new Date(val);
        if (Number.isNaN(d.getTime())) return null;
        return new Date(d.getFullYear(), d.getMonth(), d.getDate());
    };

    const fromDate = dateFrom ? toLocalDate(dateFrom) : null;
    const toDate = dateTo ? new Date(new Date(dateTo + 'T23:59:59.999')) : null;

    try {
        let source = allExpenseData || [];

        let filtered = source.filter(e => {
            const expenseDate = toLocalDate(e.expense_date);
            if (!expenseDate) return false;
            const matchDate = (!fromDate || expenseDate >= fromDate) &&
                (!toDate || expenseDate <= toDate);
            const matchCategory = !category || e.category === category;

            return matchDate && matchCategory;
        });

        renderExpenseStats(filtered);
        renderExpenseTable(filtered);
        // Баланс считаем по полным данным, чтобы не обнулять результат при фильтрах
        updateCumulativeBalance();
    } catch (error) {
        console.error('Ошибка фильтрации расходов:', error);
    }
}

// Функция сброса фильтров расходов
function resetExpenseFilters() {
    document.getElementById('expense-date-from').value = '';
    document.getElementById('expense-date-to').value = '';
    document.getElementById('expense-category-filter').value = '';
    renderExpenseStats(allExpenseData || []);
    renderExpenseTable(allExpenseData || []);
    // Сбросить баланс к полным данным
    updateCumulativeBalance();
}

// ==================== END FILTER FUNCTIONS ====================


// Модальное окно добавления расхода
const addExpenseModal = document.getElementById('addExpenseModal');
const addExpenseBtn = document.getElementById('addExpenseBtn');
const addExpenseForm = document.getElementById('addExpenseForm');

// Открыть модальное окно
if (addExpenseBtn) {
    addExpenseBtn.addEventListener('click', async () => {
        addExpenseModal.style.display = 'block';
        addExpenseForm.reset();
        await loadFinanceEmployees();
        populateExpenseEmployeeSelect('add-expense-employee');
        populateSalaryPeriod('add-expense');
        toggleSalaryEmployeeField('add-expense-category', 'add-salary-employee-group', 'add-expense-employee', 'add-salary-period-group', 'add-expense');

        // Сброс источника на кассу
        const sourceInput = document.getElementById('expense-source');
        const sourceButtons = document.querySelectorAll('#addExpenseModal .expense-source-btn');
        if (sourceInput) sourceInput.value = 'cash';
        sourceButtons.forEach(btn => {
            const isActive = btn.dataset.source === 'cash';
            btn.classList.toggle('active', isActive);
            btn.style.border = isActive ? '2px solid #ff8a00' : '2px solid #e4ddd6';
            btn.style.background = isActive ? 'linear-gradient(135deg, rgba(255, 138, 0, 0.1) 0%, rgba(217, 111, 0, 0.1) 100%)' : 'white';
            btn.style.color = isActive ? '#ff8a00' : '#4a5568';
        });

        // Показать текущий остаток наличных
        refreshCashBalanceHint();
    });
}

// Закрыть модальное окно
const closeButtons = addExpenseModal.querySelectorAll('.close');
closeButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        addExpenseModal.style.display = 'none';
    });
});

// Окно расхода закрывается только явной кнопкой.

// Отправить форму добавления расхода
addExpenseForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const formData = new FormData(addExpenseForm);
    let category = formData.get('category');
    if (category === 'Другое') {
        category = formData.get('custom_category');
    }
    const expenseSource = (formData.get('expense_source') || 'cash');
    const employeeId = formData.get('employee_id') || null;
    const salaryMonth = formData.get('salary_month') || null;
    const salaryYear = formData.get('salary_year') || null;

    const data = {
        category: category,
        amount: parseFloat(formData.get('amount')),
        description: formData.get('description') || '',
        expense_source: expenseSource,
        employee_id: category === 'Зарплата' ? employeeId : null,
        salary_month: category === 'Зарплата' ? salaryMonth : null,
        salary_year: category === 'Зарплата' ? salaryYear : null
    };

    try {
        const response = await fetch('/api/expenses/add', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            addExpenseModal.style.display = 'none';
            addExpenseForm.reset();
            // Перезагрузить данные расходов
            await loadExpenses();
            await updateCumulativeBalance();
            // Обновить баланс в шапке
            if (typeof loadBalanceBreakdown === 'function') {
                await loadBalanceBreakdown();
            }
        } else {
            const error = await response.json();
            alert('Ошибка: ' + (error.message || error.error || 'Не удалось добавить расход'));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Ошибка при добавлении расхода');
    }
});

// ==================== EDIT EXPENSE MODAL ====================
const editExpenseModal = document.getElementById('editExpenseModal');
const editExpenseForm = document.getElementById('editExpenseForm');

// Открыть модальное окно редактирования при клике на кнопку
document.addEventListener('click', async (e) => {
    const editBtn = e.target.closest('.edit-expense-btn');
    if (editBtn) {
        const btn = editBtn;
        const expenseId = btn.dataset.expenseId;
        let category = btn.dataset.category;
        const amount = btn.dataset.amount;
        const description = btn.dataset.description;
        const source = btn.dataset.source || 'cash';
        const employeeId = btn.dataset.employeeId || '';
        const salaryYear = btn.dataset.salaryYear || '';
        const salaryMonth = btn.dataset.salaryMonth || '';

        // Преобразовать Encashment обратно в Инкасация для редактирования
        if (category === 'Encashment') {
            category = 'Инкасация';
        }

        // Заполнить форму данными
        document.getElementById('edit-expense-id').value = expenseId;
        const categorySelect = document.getElementById('edit-category');
        const customGroup = document.getElementById('edit-custom-category-group');
        const customInput = document.getElementById('edit-custom-category');

        // Check if category exists in options
        const optionExists = [...categorySelect.options].some(o => o.value === category);

        if (optionExists) {
            categorySelect.value = category;
            customGroup.style.display = 'none';
            customInput.removeAttribute('required');
        } else {
            categorySelect.value = 'Другое';
            customGroup.style.display = 'block';
            customInput.value = category;
            customInput.setAttribute('required', 'required');
        }
        document.getElementById('edit-amount').value = amount;
        document.getElementById('edit-description').value = description;
        await loadFinanceEmployees();
        populateExpenseEmployeeSelect('edit-expense-employee', employeeId);
        populateSalaryPeriod('edit-expense', salaryYear ? Number(salaryYear) : null, salaryMonth ? Number(salaryMonth) : null);
        toggleSalaryEmployeeField('edit-category', 'edit-salary-employee-group', 'edit-expense-employee', 'edit-salary-period-group', 'edit-expense');

        // Установить источник
        const editSourceInput = document.getElementById('edit-expense-source');
        const sourceButtons = document.querySelectorAll('#edit-expense-source-buttons .expense-source-btn');
        if (editSourceInput) editSourceInput.value = source;
        sourceButtons.forEach(btn => {
            const isActive = btn.dataset.source === source;
            btn.classList.toggle('active', isActive);
            btn.style.border = isActive ? '2px solid #ff8a00' : '2px solid #e4ddd6';
            btn.style.background = isActive ? 'linear-gradient(135deg, rgba(255, 138, 0, 0.1) 0%, rgba(217, 111, 0, 0.1) 100%)' : 'white';
            btn.style.color = isActive ? '#ff8a00' : '#4a5568';
        });

        // Показать модальное окно
        editExpenseModal.style.display = 'block';
    }
});

// Закрыть модальное окно редактирования
const editCloseButtons = editExpenseModal.querySelectorAll('.close');
editCloseButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        editExpenseModal.style.display = 'none';
    });
});

// Окно редактирования расхода закрывается только явной кнопкой.

// Отправить форму редактирования расхода
editExpenseForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const expenseId = document.getElementById('edit-expense-id').value;
    let category = document.getElementById('edit-category').value;
    if (category === 'Другое') {
        category = document.getElementById('edit-custom-category').value;
    }
    const amount = parseFloat(document.getElementById('edit-amount').value);
    const description = document.getElementById('edit-description').value || '';
    const expenseSource = document.getElementById('edit-expense-source').value || 'cash';
    const employeeId = document.getElementById('edit-expense-employee')?.value || null;
    const salaryMonth = document.getElementById('edit-expense-salary-month')?.value || null;
    const salaryYear = document.getElementById('edit-expense-salary-year')?.value || null;

    const data = {
        category: category,
        amount: amount,
        description: description,
        expense_source: expenseSource,
        employee_id: category === 'Зарплата' ? employeeId : null,
        salary_month: category === 'Зарплата' ? salaryMonth : null,
        salary_year: category === 'Зарплата' ? salaryYear : null
    };

    try {
        const response = await fetch(`/api/expenses/${expenseId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            editExpenseModal.style.display = 'none';
            editExpenseForm.reset();
            // Перезагрузить данные расходов
            await loadExpenses();
            await updateCumulativeBalance();
            // Обновить баланс в шапке
            if (typeof loadBalanceBreakdown === 'function') {
                await loadBalanceBreakdown();
            }
            alert('Расход успешно обновлен!');
        } else {
            const error = await response.json();
            alert('Ошибка: ' + (error.message || error.error || 'Не удалось обновить расход'));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Ошибка при обновлении расхода');
    }
});

// ==================== DELETE EXPENSE ====================
document.addEventListener('click', async (e) => {
    const btn = e.target.closest('.delete-expense-btn');
    if (!btn) return;

    const expenseId = btn.dataset.expenseId;
    if (!expenseId) {
        console.error('Нет ID расхода для удаления');
        return;
    }

    if (!confirm('Удалить этот расход без возможности восстановления?')) {
        return;
    }

    try {
        const response = await fetch(`/api/expenses/${expenseId}`, { method: 'DELETE' });
        const result = await response.json();
        if (response.ok && result.success) {
            await loadExpenses();
            await updateCumulativeBalance();
            // Обновить баланс в шапке
            if (typeof loadBalanceBreakdown === 'function') {
                await loadBalanceBreakdown();
            }
            alert('Расход удалён');
        } else {
            alert('Ошибка: ' + (result.message || 'Не удалось удалить расход'));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Ошибка при удалении расхода');
    }
});

// ==================== DELETE INCOME ====================
document.addEventListener('click', async (e) => {
    if (e.target.classList.contains('delete-income-btn')) {
        const btn = e.target;
        const paymentId = btn.dataset.paymentId;

        if (!confirm('Вы уверены, что хотите удалить этот платеж?')) {
            return;
        }

        try {
            const response = await fetch(`/api/payments/${paymentId}/delete`, {
                method: 'DELETE'
            });

            if (response.ok) {
                await loadIncome();
                await loadDebtors();
                alert('Платеж успешно удален!');
            } else {
                const error = await response.json();
                alert('Ошибка: ' + (error.error || 'Не удалось удалить платеж'));
            }
        } catch (error) {
            console.error('Error:', error);
            alert('Ошибка при удалении платежа');
        }
    }
});

// ==================== EDIT INCOME MODAL ====================
const editIncomeModal = document.getElementById('editIncomeModal');
const editIncomeForm = document.getElementById('editIncomeForm');

// Открыть модальное окно редактирования прихода
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('edit-income-btn')) {
        const btn = e.target;
        const paymentId = btn.dataset.paymentId;
        const studentId = btn.dataset.studentId;
        const amount = btn.dataset.amount;
        const notes = btn.dataset.notes;

        // Заполнить форму данными
        document.getElementById('edit-payment-id').value = paymentId;
        document.getElementById('edit-student-id').value = studentId;
        const editAmountInput = document.getElementById('edit-payment-amount');
        if (editAmountInput) {
            editAmountInput.value = amount;
            formatAmountInputValue(editAmountInput);
        }
        document.getElementById('edit-payment-notes').value = notes;

        // Показать модальное окно
        editIncomeModal.style.display = 'block';
    }
});

// Закрыть модальное окно редактирования прихода
const editIncomeCloseButtons = editIncomeModal.querySelectorAll('.close');
editIncomeCloseButtons.forEach(btn => {
    btn.addEventListener('click', () => {
        editIncomeModal.style.display = 'none';
    });
});

// Окно редактирования оплаты закрывается только явной кнопкой.

// Отправить форму редактирования прихода
editIncomeForm.addEventListener('submit', async (e) => {
    e.preventDefault();

    const paymentId = document.getElementById('edit-payment-id').value;
    const studentId = document.getElementById('edit-student-id').value;
    const amount = sanitizeAmountValue(document.getElementById('edit-payment-amount').value);
    const notes = document.getElementById('edit-payment-notes').value || '';

    const data = {
        student_id: parseInt(studentId),
        amount: amount,
        notes: notes
    };

    try {
        const response = await fetch(`/api/payments/${paymentId}/update`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(data)
        });

        if (response.ok) {
            editIncomeModal.style.display = 'none';
            editIncomeForm.reset();
            // Перезагрузить данные прихода
            loadIncome();
            alert('Платеж успешно обновлен!');
        } else {
            const error = await response.json();
            alert('Ошибка: ' + (error.error || 'Не удалось обновить платеж'));
        }
    } catch (error) {
        console.error('Error:', error);
        alert('Ошибка при обновлении платежа');
    }
});

// ==================== EXPENSE CATEGORY TOGGLE ====================

function setupCategoryToggle(selectId, customGroupId, inputName) {
    const select = document.getElementById(selectId);
    const customGroup = document.getElementById(customGroupId);

    if (!select || !customGroup) return;

    // Find the input within the group or by ID if specific
    const input = customGroup.querySelector('input');

    select.addEventListener('change', () => {
        if (select.value === 'Другое') {
            customGroup.style.display = 'block';
            if (input) input.setAttribute('required', 'required');
        } else {
            customGroup.style.display = 'none';
            if (input) input.removeAttribute('required');
        }
    });
}

// Initialize toggles
document.addEventListener('DOMContentLoaded', () => {
    setupCategoryToggle('add-expense-category', 'add-custom-category-group', 'custom_category');
    setupCategoryToggle('edit-category', 'edit-custom-category-group', 'custom_category');
    const addExpenseCategory = document.getElementById('add-expense-category');
    const editExpenseCategory = document.getElementById('edit-category');
    if (addExpenseCategory) {
        addExpenseCategory.addEventListener('change', () => {
            toggleSalaryEmployeeField('add-expense-category', 'add-salary-employee-group', 'add-expense-employee', 'add-salary-period-group', 'add-expense');
        });
    }
    if (editExpenseCategory) {
        editExpenseCategory.addEventListener('change', () => {
            toggleSalaryEmployeeField('edit-category', 'edit-salary-employee-group', 'edit-expense-employee', 'edit-salary-period-group', 'edit-expense');
        });
    }

    const enforceIncassoSource = (selectId, hiddenInputId, containerSelector) => {
        const select = document.getElementById(selectId);
        const hidden = document.getElementById(hiddenInputId);
        const container = document.querySelector(containerSelector);
        if (!select || !hidden || !container) return;

        const apply = () => {
            if (select.value === 'Инкасация') {
                hidden.value = 'cash';
                container.querySelectorAll('.expense-source-btn').forEach(btn => {
                    const isCash = btn.dataset.source === 'cash';
                    btn.classList.toggle('active', isCash);
                    btn.style.border = isCash ? '2px solid #ff8a00' : '2px solid #e4ddd6';
                    btn.style.background = isCash ? 'linear-gradient(135deg, rgba(255, 138, 0, 0.1) 0%, rgba(217, 111, 0, 0.1) 100%)' : 'white';
                    btn.style.color = isCash ? '#ff8a00' : '#4a5568';
                    btn.disabled = !isCash;
                    btn.style.opacity = isCash ? '1' : '0.5';
                });
            } else {
                container.querySelectorAll('.expense-source-btn').forEach(btn => {
                    btn.disabled = false;
                    btn.style.opacity = '1';
                });
            }
        };

        select.addEventListener('change', apply);
        apply();
    };

    // Переключатели источника расходов
    function bindExpenseSourceButtons(containerSelector, hiddenInputId) {
        const container = document.querySelector(containerSelector);
        const hiddenInput = document.getElementById(hiddenInputId);
        if (!container || !hiddenInput) return;

        container.querySelectorAll('.expense-source-btn').forEach(btn => {
            btn.addEventListener('click', () => {
                const source = btn.dataset.source || 'cash';
                hiddenInput.value = source;

                container.querySelectorAll('.expense-source-btn').forEach(b => {
                    const isActive = b === btn;
                    b.classList.toggle('active', isActive);
                    b.style.border = isActive ? '2px solid #ff8a00' : '2px solid #e4ddd6';
                    b.style.background = isActive ? 'linear-gradient(135deg, rgba(255, 138, 0, 0.1) 0%, rgba(217, 111, 0, 0.1) 100%)' : 'white';
                    b.style.color = isActive ? '#ff8a00' : '#4a5568';
                });
            });
        });
    }

    bindExpenseSourceButtons('#addExpenseModal .expense-source-buttons', 'expense-source');
    bindExpenseSourceButtons('#edit-expense-source-buttons', 'edit-expense-source');
    enforceIncassoSource('add-expense-category', 'expense-source', '#addExpenseModal .expense-source-buttons');
    enforceIncassoSource('edit-category', 'edit-expense-source', '#edit-expense-source-buttons');
});

// Функция для обновления накопительного баланса
async function updateCumulativeBalance() {
    try {
        const res = await fetch('/api/finances/balance');
        if (!res.ok) throw new Error('balance endpoint failed');
        const data = await res.json();

        const total = Number(data.total_balance || 0);
        const cashBalance = Number(data.cash_balance || 0);
        const bankBalance = Number(data.bank_balance || 0);

        const balanceElement = document.getElementById('cumulativeBalance');
        const cashEl = document.getElementById('cashBalanceValue');
        const bankEl = document.getElementById('bankBalanceValue');

        if (balanceElement) {
            balanceElement.textContent = `${total.toLocaleString('ru-RU')} сум`;
            balanceElement.style.color = total < 0 ? '#ef4444' : '#1e293b';
        }
        if (cashEl) cashEl.textContent = `${cashBalance.toLocaleString('ru-RU')} сум`;
        if (bankEl) bankEl.textContent = `${bankBalance.toLocaleString('ru-RU')} сум`;
    } catch (error) {
        console.error('Ошибка при обновлении баланса:', error);

        // Фоллбек на старую логику, если новый эндпоинт недоступен
        try {
            let totalIncome = 0;
            let totalExpenses = 0;

            if (Array.isArray(allIncomeData) && allIncomeData.length > 0) {
                totalIncome = allIncomeData.reduce((sum, payment) => sum + (parseFloat(payment.amount_paid) || 0), 0);
            } else {
                const incomeResponse = await fetch('/api/finances/income');
                const incomeData = await incomeResponse.json();
                totalIncome = parseFloat(incomeData.total) || 0;
            }

            if (Array.isArray(allExpenseData) && allExpenseData.length > 0) {
                totalExpenses = allExpenseData.reduce((sum, expense) => sum + (parseFloat(expense.amount) || 0), 0);
            } else {
                const expensesResponse = await fetch('/api/finances/expenses');
                const expensesData = await expensesResponse.json();
                totalExpenses = parseFloat(expensesData.total) || 0;
            }

            const balance = totalIncome - totalExpenses;
            const balanceElement = document.getElementById('cumulativeBalance');
            if (balanceElement) {
                balanceElement.textContent = `${balance.toLocaleString('ru-RU')} сум`;
                balanceElement.style.color = balance < 0 ? '#ef4444' : '#1e293b';
            }
        } catch (e) {
            console.error('Фоллбек баланс также упал:', e);
        }
    }
}

// Показать текущий остаток наличных в форме расхода
async function refreshCashBalanceHint() {
    const hint = document.getElementById('cash-balance-hint');
    if (!hint) return;

    try {
        const res = await fetch('/api/finances/balance');
        if (!res.ok) throw new Error('balance endpoint failed');
        const data = await res.json();
        const cashBalance = Number(data.cash_balance || 0);
        hint.textContent = `Наличные в кассе: ${cashBalance.toLocaleString('ru-RU')} сум`;
        hint.style.color = cashBalance < 0 ? '#ef4444' : '#4a5568';
    } catch (error) {
        console.error('Ошибка при получении остатка кассы:', error);
        hint.textContent = 'Наличные в кассе: —';
        hint.style.color = '#4a5568';
    }
}

// Вызвать функцию при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    updateCumulativeBalance();
    initMobileFilters();
});

// ==================== MOBILE FILTER MODAL ====================
function initMobileFilters() {
    const overlay = document.getElementById('filterModalOverlay');
    const bottomSheet = document.getElementById('filterBottomSheet');
    const closeBtn = document.getElementById('closeFilterModal');
    const modalContent = document.getElementById('filterModalContent');
    const body = document.body;

    if (!overlay || !bottomSheet || !modalContent) {
        return;
    }

    let activeFilterPanel = null;
    let activeFilterContent = null;

    // Глобальная функция открытия модального окна с фильтрами
    window.openFilterModal = function (filterPanelId, title) {
        const filterPanel = document.getElementById(filterPanelId);
        if (!filterPanel) return false;

        const filterContent = filterPanel.querySelector('.filter-panel-content');
        if (!filterContent) return false;

        // Устанавливаем заголовок
        const titleEl = document.getElementById('filterModalTitle');
        if (titleEl) {
            titleEl.textContent = title;
        }

        // Перемещаем контент фильтров в модалку
        modalContent.innerHTML = '';
        modalContent.appendChild(filterContent);

        activeFilterPanel = filterPanel;
        activeFilterContent = filterContent;

        // Показываем модальное окно
        overlay.classList.add('active');
        body.classList.add('mobile-filter-open');
        setTimeout(() => bottomSheet.classList.add('active'), 10);

        return true;
    };

    // Функция закрытия модального окна
    function closeFilterModal() {
        bottomSheet.classList.remove('active');
        setTimeout(() => {
            overlay.classList.remove('active');
            body.classList.remove('mobile-filter-open');

            // Возвращаем контент фильтров обратно
            if (activeFilterPanel && activeFilterContent) {
                activeFilterPanel.appendChild(activeFilterContent);
            }

            modalContent.innerHTML = '';
            activeFilterPanel = null;
            activeFilterContent = null;
        }, 300);
    }

    // Закрытие по клику на overlay
    overlay.addEventListener('click', closeFilterModal);

    // Закрытие по кнопке
    if (closeBtn) {
        closeBtn.addEventListener('click', closeFilterModal);
    }

    // Обработка кликов на кнопки внутри модального окна
    modalContent.addEventListener('click', (e) => {
        const button = e.target.closest('button');
        if (!button) return;

        const onclickStr = button.getAttribute('onclick');

        // Закрываем после применения/сброса
        if (onclickStr || button.textContent.includes('Сбросить')) {
            setTimeout(() => closeFilterModal(), 100);
        }
    });
}
