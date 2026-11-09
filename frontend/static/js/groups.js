// Безопасный вывод текста в HTML. На странице настроек функция уже есть (settings.js),
// на отдельных страницах групп/тарифов/вознаграждений — объявляем здесь.
if (typeof window.escapeHtml !== 'function') {
    window.escapeHtml = (value) => String(value ?? '')
        .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
}

const DAY_LABELS = { 1: 'Пн', 2: 'Вт', 3: 'Ср', 4: 'Чт', 5: 'Пт', 6: 'Сб', 7: 'Вс' };
const groupEditIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"/></svg>';
const groupTrashIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M19 6l-1 14H6L5 6"/><path d="M10 11v5"/><path d="M14 11v5"/></svg>';
const groupPhoneIcon = '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M22 16.92v3a2 2 0 0 1-2.18 2 19.8 19.8 0 0 1-8.63-3.07 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.12 4.18 2 2 0 0 1 4.11 2h3a2 2 0 0 1 2 1.72c.13.96.35 1.9.65 2.8a2 2 0 0 1-.45 2.11L8.09 9.91a16 16 0 0 0 6 6l1.27-1.27a2 2 0 0 1 2.11-.45c.9.3 1.84.52 2.8.65A2 2 0 0 1 22 16.92Z"/></svg>';
let clubSettings = {
    working_days: [1, 2, 3, 4, 5],
    work_start_time: '09:00',
    work_end_time: '21:00',
    max_groups_per_slot: 4
};
let allGroups = [];
let allTrainers = [];

// Для блоков стадиона
let selectedFieldBlocks = [];
let editSelectedFieldBlocks = [];

function hasMixedTimes(slots) {
    if (!slots || !slots.length) return false;
    const first = slots[0].time;
    return slots.some(s => s.time !== first);
}

// Функция для форматирования времени группы
// «17:00:00» → «17:00»: секунды в расписании никому не нужны.
const trimSeconds = (time) => String(time ?? '').replace(/^(\d{1,2}:\d{2}):\d{2}$/, '$1');

function formatGroupScheduleTime(scheduleTime) {
    if (!scheduleTime) return '—';
    
    // Проверяем, является ли это JSON объектом
    if (typeof scheduleTime === 'string' && scheduleTime.startsWith('{')) {
        try {
            const timeMap = JSON.parse(scheduleTime);
            const times = Object.values(timeMap);
            const uniqueTimes = [...new Set(times.map(trimSeconds))];
            
            if (uniqueTimes.length === 1) {
                // Все времена одинаковые
                return uniqueTimes[0];
            } else {
                // Разные времена - показываем список
                const entries = Object.entries(timeMap).map(([day, time]) => `${DAY_LABELS[day]} ${trimSeconds(time)}`);
                return entries.join(', ');
            }
        } catch (e) {
            return scheduleTime;
        }
    }
    
    return trimSeconds(scheduleTime);
}

function describeDays(days) {
    if (!days || days.length === 0) return '-';
    return days.map(day => DAY_LABELS[day] || day).join(', ');
}

function getMultiSelectValues(id) {
    const select = document.getElementById(id);
    if (!select) return [];
    return Array.from(select.selectedOptions).map(option => parseInt(option.value)).filter(Boolean);
}

function renderTrainerSelect(id, selectedIds = []) {
    const select = document.getElementById(id);
    if (!select) return;
    const selectedSet = new Set((selectedIds || []).map(value => String(value)));
    select.classList.add('native-multi-select');
    select.innerHTML = allTrainers.map(trainer => `
        <option value="${trainer.id}" ${selectedSet.has(String(trainer.id)) ? 'selected' : ''}>
            ${escapeHtml(trainer.full_name || trainer.username)}
        </option>
    `).join('');
    renderTrainerChecklist(id);
}

function renderTrainerChecklist(selectId) {
    const select = document.getElementById(selectId);
    const list = document.getElementById(`${selectId}Checklist`);
    if (!select || !list) return;

    const options = Array.from(select.options);
    if (!options.length) {
        list.innerHTML = '<div class="trainer-check-empty">Нет тренеров</div>';
        return;
    }

    list.innerHTML = options.map(option => {
        const trainer = allTrainers.find(item => String(item.id) === String(option.value)) || {};
        const displayName = option.textContent.trim();
        const initial = (displayName || 'Т').trim().slice(0, 1).toUpperCase();
        const avatar = trainer.photo_url
            ? `<img class="trainer-check-avatar" src="${escapeHtml(trainer.photo_url)}" alt="" loading="lazy" decoding="async">`
            : `<span class="trainer-check-avatar trainer-check-avatar-fallback">${escapeHtml(initial)}</span>`;
        return `
        <label class="trainer-check-option">
            <input type="checkbox" value="${escapeHtml(option.value)}" ${option.selected ? 'checked' : ''}>
            ${avatar}
            <span class="trainer-check-name">${escapeHtml(displayName)}</span>
        </label>
    `;
    }).join('');

    list.querySelectorAll('input[type="checkbox"]').forEach(checkbox => {
        checkbox.addEventListener('change', () => {
            const option = Array.from(select.options).find(item => String(item.value) === String(checkbox.value));
            if (option) option.selected = checkbox.checked;
        });
    });
}

function refreshTrainerSelects(group = null) {
    renderTrainerSelect('groupTrainerIds', group?.trainer_ids || []);
    renderTrainerSelect('groupAssistantIds', group?.assistant_ids || []);
    renderTrainerSelect('editGroupTrainerIds', group?.trainer_ids || []);
    renderTrainerSelect('editGroupAssistantIds', group?.assistant_ids || []);
}

async function loadTrainers() {
    try {
        const response = await fetch('/api/trainers');
        if (!response.ok) throw new Error('Ошибка загрузки тренеров');
        allTrainers = await response.json();
        refreshTrainerSelects();
    } catch (error) {
        console.error('Ошибка загрузки тренеров:', error);
        allTrainers = [];
        refreshTrainerSelects();
    }
}

function setWeekdaySelection(target, days) {
    const boxes = document.querySelectorAll(`.weekday-checkbox[data-target="${target}"]`);
    boxes.forEach(box => {
        box.checked = days.includes(parseInt(box.value));
    });
}

function getSelectedDays(target) {
    const boxes = document.querySelectorAll(`.weekday-checkbox[data-target="${target}"]`);
    return Array.from(boxes)
        .filter(box => box.checked)
        .map(box => parseInt(box.value));
}

function updateWorkingHoursHint() {
    const hint = document.getElementById('workingHoursHint');
    if (hint) {
        hint.textContent = `Рабочее время клуба: ${clubSettings.work_start_time} – ${clubSettings.work_end_time}. Максимум ${clubSettings.max_groups_per_slot} групп.`;
    }
}

function generateTimeSlots() {
    const slots = [];
    const [startHour, startMin] = clubSettings.work_start_time.split(':').map(Number);
    const [endHour, endMin] = clubSettings.work_end_time.split(':').map(Number);
    
    let currentHour = startHour;
    while (currentHour < endHour || (currentHour === endHour && 0 < endMin)) {
        const time = `${String(currentHour).padStart(2, '0')}:00`;
        slots.push(time);
        currentHour++;
    }
    
    return slots;
}

function getSlotOccupancy(day, time) {
    const groupsAtSlot = allGroups.filter(g => {
        if (!g.schedule_days.includes(day)) return false;
        
        const duration = g.duration_minutes || 60;
        const slotStart = parseTime(time);
        const slotEnd = addMinutes(slotStart, 60); // Каждая ячейка = 1 час
        
        const groupStart = parseTime(g.schedule_time);
        const groupEnd = addMinutes(groupStart, duration);
        
        // Проверяем пересечение временных интервалов
        return (groupStart < slotEnd && groupEnd > slotStart);
    });
    return groupsAtSlot.length;
}

function parseTime(timeStr) {
    const [hours, minutes] = timeStr.split(':').map(Number);
    return hours * 60 + minutes;
}

function addMinutes(timeInMinutes, minutes) {
    return timeInMinutes + minutes;
}

let selectedSlots = []; // Массив объектов {day, time}

function selectTimeSlot(day, time) {
    const occupancy = getSlotOccupancy(day, time);
    const maxGroups = clubSettings.max_groups_per_slot;
    
    // Нельзя выбрать полностью занятый слот
    if (occupancy >= maxGroups) return;
    
    // Проверяем, выбран ли уже этот слот
    const slotIndex = selectedSlots.findIndex(s => s.day === day && s.time === time);
    
    if (slotIndex >= 0) {
        // Если уже выбран - убираем
        selectedSlots.splice(slotIndex, 1);
    } else {
        // Проверяем, есть ли уже время для этого дня
        const existingDayIndex = selectedSlots.findIndex(s => s.day === day);
        if (existingDayIndex >= 0) {
            // Заменяем время для этого дня
            selectedSlots[existingDayIndex].time = time;
        } else {
            // Добавляем новый слот
            selectedSlots.push({ day, time });
        }
    }
    
    updateHiddenFields();
    renderScheduleVisualization();
    updateSelectedSlotsDisplay();
    renderFieldBlocks();
    updateFieldBlocksInfo();
}

function removeSlot(day) {
    selectedSlots = selectedSlots.filter(s => s.day !== day);
    updateHiddenFields();
    renderScheduleVisualization();
    updateSelectedSlotsDisplay();
    renderFieldBlocks();
    updateFieldBlocksInfo();
}

function updateHiddenFields() {
    // Группируем по времени (если все дни на одно время)
    const uniqueTimes = [...new Set(selectedSlots.map(s => s.time))];
    const days = selectedSlots.map(s => s.day);
    
    document.getElementById('scheduleDays').value = JSON.stringify(days);
    document.getElementById('scheduleTime').value = uniqueTimes.length === 1 ? uniqueTimes[0] : JSON.stringify(selectedSlots);
}

function updateSelectedSlotsDisplay() {
    const container = document.getElementById('selectedSlotsDisplay');
    if (!container) return;
    
    if (selectedSlots.length === 0) {
        container.innerHTML = '';
        return;
    }
    
    // Сортируем по дню
    const sorted = [...selectedSlots].sort((a, b) => a.day - b.day);
    
    container.innerHTML = sorted.map(slot => `
        <div class="selected-slot-badge">
            ${DAY_LABELS[slot.day]} ${slot.time}
            <span class="remove-slot" onclick="removeSlot(${slot.day})" title="Удалить">✕</span>
        </div>
    `).join('');
}

function renderScheduleVisualization() {
    const container = document.getElementById('scheduleVisualization');
    if (!container) return;
    
    const timeSlots = generateTimeSlots();
    const maxGroups = clubSettings.max_groups_per_slot;
    
    let html = '<div class="schedule-grid">';
    
    // Header row
    html += '<div class="schedule-header"></div>'; // Empty corner
    for (let day = 1; day <= 7; day++) {
        html += `<div class="schedule-header">${DAY_LABELS[day]}</div>`;
    }
    
    // Time slots
    timeSlots.forEach(time => {
        html += `<div class="schedule-time-label">${time}</div>`;
        
        for (let day = 1; day <= 7; day++) {
            const occupancy = getSlotOccupancy(day, time);
            let slotClass = '';
            let slotText = '';
            
            // Проверяем, выбрана ли эта ячейка
            const isSelected = selectedSlots.some(s => s.day === day && s.time === time);
            
            // Проверяем, выбран ли другой слот в этом дне
            const otherTimeSelected = selectedSlots.some(s => s.day === day && s.time !== time);
            
            if (isSelected) {
                slotClass = 'selected';
                slotText = '✓ Выбрано';
            } else if (otherTimeSelected) {
                // Если выбрано другое время в этом дне - делаем серым
                slotClass = 'disabled';
                if (occupancy >= maxGroups) {
                    slotText = 'Занято';
                } else if (occupancy > 0) {
                    slotText = `${occupancy}/${maxGroups}`;
                } else {
                    slotText = 'Свободно';
                }
            } else if (occupancy >= maxGroups) {
                slotClass = 'occupied';
                slotText = 'Занято';
            } else if (occupancy > 0) {
                slotClass = 'partial';
                slotText = `${occupancy}/${maxGroups}`;
            } else {
                slotClass = 'free';
                slotText = 'Свободно';
            }
            
            const clickHandler = (occupancy < maxGroups) ? `onclick="selectTimeSlot(${day}, '${time}')"` : '';
            html += `<div class="schedule-slot ${slotClass}" ${clickHandler} title="${DAY_LABELS[day]} ${time}: ${slotText}">${slotText}</div>`;
        }
    });
    
    html += '</div>';
    
    // Legend
    html += `
        <div class="schedule-legend">
            <div class="schedule-legend-item">
                <div class="schedule-legend-box free"></div>
                <span>Свободно</span>
            </div>
            <div class="schedule-legend-item">
                <div class="schedule-legend-box partial"></div>
                <span>Частично занято</span>
            </div>
            <div class="schedule-legend-item">
                <div class="schedule-legend-box occupied"></div>
                <span>Полностью занято</span>
            </div>
        </div>
    `;
    
    container.innerHTML = html;
}

async function loadClubSettings() {
    try {
        console.log('⚙️ Загрузка настроек клуба...');
        const response = await fetch('/api/club-settings');
        const data = await response.json();
        clubSettings = data;
        console.log('✅ Настройки клуба загружены:', clubSettings);
        updateWorkingHoursHint();
        setWeekdaySelection('settings', clubSettings.working_days);
        const workStartEl = document.getElementById('workStartTime');
        const workEndEl = document.getElementById('workEndTime');
        const maxGroupsEl = document.getElementById('maxGroupsPerSlot');
        const blockFutureEl = document.getElementById('blockFuturePayments');
        if (workStartEl) workStartEl.value = clubSettings.work_start_time;
        if (workEndEl) workEndEl.value = clubSettings.work_end_time;
        if (maxGroupsEl) maxGroupsEl.value = clubSettings.max_groups_per_slot;
        if (blockFutureEl) blockFutureEl.checked = !!clubSettings.block_future_payments;
    } catch (error) {
        console.error('❌ Ошибка загрузки настроек клуба:', error);
    }
}

async function loadGroups() {
    try {
        const response = await fetch('/api/groups');
        const groups = await response.json();
        allGroups = groups; // Сохраняем для визуализации расписания
        
        const tbody = document.getElementById('groupsTableBody');
        
        if (!groups.length) {
            tbody.innerHTML = '<tr><td colspan="8">Нет групп</td></tr>';
            return;
        }
        
        tbody.innerHTML = groups.map(group => {
            let studentsDisplay = group.active_student_count || group.student_count || 0;
            if (group.max_students) {
                const isFull = group.is_full;
                const color = isFull ? '#e74c3c' : (group.active_student_count / group.max_students > 0.8 ? '#ff8a00' : '#27ae60');
                studentsDisplay = `<span style="color: ${color}; font-weight: bold;">${group.active_student_count}/${group.max_students}</span>`;
            }
            
            const formattedTime = formatGroupScheduleTime(group.schedule_time);
            const trainerNames = [
                ...(group.trainers || []).map(trainer => trainer.full_name),
                ...(group.assistants || []).map(trainer => `${trainer.full_name} (пом.)`)
            ].filter(Boolean).join(', ') || '-';
            
            return `
            <tr>
                <td><strong>${escapeHtml(group.name)}</strong></td>
                <td>${group.schedule_days_label || describeDays(group.schedule_days)}</td>
                <td>${formattedTime}</td>
                <td><small style="color:#64748b;">${escapeHtml(trainerNames)}</small></td>
                <td>${group.late_threshold}</td>
                <td>${studentsDisplay}</td>
                <td>${group.notes ? escapeHtml(group.notes) : '-'}</td>
                <td>
                    <button class="btn-small btn-success" data-group-name="${escapeHtml(group.name)}" onclick="sendGroupNotification(${group.id}, this.dataset.groupName)" title="Отправить уведомления в Telegram">${groupPhoneIcon}</button>
                    <button class="btn-small btn-info" onclick="editGroup(${group.id})" title="Редактировать">${groupEditIcon}</button>
                    <button class="btn-small btn-danger" data-group-name="${escapeHtml(group.name)}" onclick="deleteGroup(${group.id}, this.dataset.groupName)" title="Удалить">${groupTrashIcon}</button>
                </td>
            </tr>
        `}).join('');
    } catch (error) {
        console.error('Ошибка загрузки групп:', error);
    }
}

function showAddGroupModal() {
    console.log('📝 Открытие модального окна добавления группы');
    console.log('clubSettings:', clubSettings);
    selectedSlots = [];
    selectedFieldBlocks = [];
    document.getElementById('scheduleTime').value = '';
    document.getElementById('scheduleDays').value = '';
    document.getElementById('fieldBlocks').value = '';
    document.getElementById('slotValidationMessage').style.display = 'none';
    refreshTrainerSelects();
    document.getElementById('addGroupModal').style.display = 'block';
    updateSelectedSlotsDisplay();
    renderScheduleVisualization();
    renderFieldBlocks();
    updateFieldBlocksInfo();
}

function closeAddGroupModal() {
    selectedSlots = [];
    selectedFieldBlocks = [];
    document.getElementById('addGroupModal').style.display = 'none';
    document.getElementById('addGroupForm').reset();
    document.getElementById('slotValidationMessage').style.display = 'none';
    updateSelectedSlotsDisplay();
}

document.getElementById('addGroupForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    console.log('🔍 Отправка формы добавления группы...');
    console.log('Selected slots:', selectedSlots);
    console.log('Selected field blocks:', selectedFieldBlocks);
    
    const alertBox = document.getElementById('slotValidationMessage');
    alertBox.style.display = 'none';
    
    if (selectedSlots.length === 0) {
        console.log('❌ Не выбраны слоты расписания');
        alertBox.textContent = 'Выберите хотя бы один день и время из расписания';
        alertBox.style.display = 'block';
        return;
    }
    
    if (selectedFieldBlocks.length === 0) {
        console.log('❌ Не выбраны блоки стадиона');
        alertBox.textContent = 'Выберите хотя бы один блок стадиона';
        alertBox.style.display = 'block';
        return;
    }
    
    const data = {
        name: document.getElementById('groupName').value,
        duration_minutes: parseInt(document.getElementById('durationMinutes').value),
        // Для совместимости оставляем field_blocks, но главное — field_block_indices
        field_blocks: selectedFieldBlocks.length,
        field_block_indices: selectedFieldBlocks,
        schedule_time: document.getElementById('scheduleTime').value,
        late_threshold: document.getElementById('lateThreshold').value,
        max_students: document.getElementById('maxStudents').value || null,
        trainer_ids: getMultiSelectValues('groupTrainerIds'),
        assistant_ids: getMultiSelectValues('groupAssistantIds'),
        notes: document.getElementById('notes').value,
        schedule_days: JSON.parse(document.getElementById('scheduleDays').value)
    };
    
    try {
        const response = await fetch('/api/groups/add', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {
            alert('✓ Группа добавлена!');
            closeAddGroupModal();
            loadGroups();
        } else {
            alertBox.textContent = result.message;
            alertBox.style.display = 'block';
        }
    } catch (error) {
        console.error('Ошибка:', error);
        alertBox.textContent = 'Ошибка при добавлении группы';
        alertBox.style.display = 'block';
    }
});

// Для окна редактирования
let editSelectedSlots = [];

function selectEditTimeSlot(day, time) {
    // Удаляем предыдущие выборы для этого дня
    editSelectedSlots = editSelectedSlots.filter(s => s.day !== day);
    // Добавляем новый выбор
    editSelectedSlots.push({ day, time });
    updateEditHiddenFields();
    updateEditSelectedSlotsDisplay();
    renderEditScheduleVisualization();
    renderEditFieldBlocks();
    updateEditFieldBlocksInfo();
}

function removeEditSlot(day) {
    editSelectedSlots = editSelectedSlots.filter(s => s.day !== day);
    updateEditHiddenFields();
    updateEditSelectedSlotsDisplay();
    renderEditScheduleVisualization();
    renderEditFieldBlocks();
    updateEditFieldBlocksInfo();
}

function updateEditHiddenFields() {
    if (editSelectedSlots.length === 0) {
        document.getElementById('editScheduleTime').value = '';
        document.getElementById('editScheduleDays').value = '';
        return;
    }
    
    const days = editSelectedSlots.map(s => s.day);
    const times = editSelectedSlots.map(s => s.time);
    
    // Проверяем, все ли времена одинаковые
    const allSameTime = times.every(t => t === times[0]);
    
    if (allSameTime) {
        document.getElementById('editScheduleTime').value = times[0];
    } else {
        // Если разные времена, сохраняем JSON
        const timeMap = {};
        editSelectedSlots.forEach(s => {
            timeMap[s.day] = s.time;
        });
        document.getElementById('editScheduleTime').value = JSON.stringify(timeMap);
    }
    
    document.getElementById('editScheduleDays').value = JSON.stringify(days);
}

function updateEditSelectedSlotsDisplay() {
    const container = document.getElementById('editSelectedSlotsDisplay');
    if (editSelectedSlots.length === 0) {
        container.innerHTML = '<div class="no-selection">Выберите дни и время в расписании ниже</div>';
        return;
    }
    
    let html = '<div class="selected-slots-badges">';
    editSelectedSlots.forEach(slot => {
        html += `
            <div class="slot-badge">
                <span class="slot-badge-text">${DAY_LABELS[slot.day]} ${slot.time}</span>
                <button type="button" class="slot-badge-remove" onclick="removeEditSlot(${slot.day})" title="Удалить">&times;</button>
            </div>
        `;
    });
    html += '</div>';
    container.innerHTML = html;
}

function renderEditScheduleVisualization() {
    const container = document.getElementById('editScheduleVisualization');
    if (!clubSettings || !allGroups) {
        container.innerHTML = '<div class="schedule-loading">Загрузка расписания...</div>';
        return;
    }
    
    const workingDays = clubSettings.working_days;
    const startTime = clubSettings.work_start_time;
    const endTime = clubSettings.work_end_time;
    const timeSlots = generateTimeSlots(startTime, endTime);
    const maxGroups = clubSettings.max_groups_per_slot;
    
    // Получаем ID редактируемой группы для исключения из подсчета занятости
    const editGroupId = parseInt(document.getElementById('editGroupId').value);
    
    let html = '<div class="schedule-grid">';
    
    // Header row
    html += '<div class="schedule-header"></div>';
    for (let day = 1; day <= 7; day++) {
        html += `<div class="schedule-header">${DAY_LABELS[day]}</div>`;
    }
    
    // Time slots
    timeSlots.forEach(time => {
        html += `<div class="schedule-time-label">${time}</div>`;
        
        for (let day = 1; day <= 7; day++) {
            // Считаем занятость, исключая редактируемую группу
            const occupancy = getSlotOccupancyExcluding(day, time, editGroupId);
            let slotClass = '';
            let slotText = '';
            
            const isSelected = editSelectedSlots.some(s => s.day === day && s.time === time);
            const otherTimeSelected = editSelectedSlots.some(s => s.day === day && s.time !== time);
            
            if (isSelected) {
                slotClass = 'selected';
                slotText = '✓ Выбрано';
            } else if (otherTimeSelected) {
                slotClass = 'disabled';
                if (occupancy >= maxGroups) {
                    slotText = 'Занято';
                } else if (occupancy > 0) {
                    slotText = `${occupancy}/${maxGroups}`;
                } else {
                    slotText = 'Свободно';
                }
            } else if (occupancy >= maxGroups) {
                slotClass = 'occupied';
                slotText = 'Занято';
            } else if (occupancy > 0) {
                slotClass = 'partial';
                slotText = `${occupancy}/${maxGroups}`;
            } else {
                slotClass = 'free';
                slotText = 'Свободно';
            }
            
            const clickHandler = (occupancy < maxGroups) ? `onclick="selectEditTimeSlot(${day}, '${time}')"` : '';
            html += `<div class="schedule-slot ${slotClass}" ${clickHandler} title="${DAY_LABELS[day]} ${time}: ${slotText}">${slotText}</div>`;
        }
    });
    
    html += '</div>';
    
    html += `
        <div class="schedule-legend">
            <div class="schedule-legend-item">
                <div class="schedule-legend-box free"></div>
                <span>Свободно</span>
            </div>
            <div class="schedule-legend-item">
                <div class="schedule-legend-box partial"></div>
                <span>Частично занято</span>
            </div>
            <div class="schedule-legend-item">
                <div class="schedule-legend-box occupied"></div>
                <span>Полностью занято</span>
            </div>
        </div>
    `;
    
    container.innerHTML = html;
}

function getSlotOccupancyExcluding(day, time, excludeGroupId) {
    if (!allGroups || !clubSettings) return 0;
    
    const durationMinutes = parseInt(document.getElementById('editDurationMinutes').value) || 60;
    const slotStart = parseTime(time);
    const slotEnd = addMinutes(slotStart, durationMinutes);
    
    let count = 0;
    allGroups.forEach(group => {
        // Исключаем редактируемую группу из подсчета
        if (group.id === excludeGroupId) return;
        
        const groupDays = group.schedule_days || [];
        if (!groupDays.includes(day)) return;
        
        const groupDuration = group.duration_minutes || 60;
        const groupStart = parseTime(group.schedule_time);
        const groupEnd = addMinutes(groupStart, groupDuration);
        
        if (groupStart < slotEnd && groupEnd > slotStart) {
            count++;
        }
    });
    
    return count;
}

async function editGroup(groupId) {
    try {
        const response = await fetch('/api/groups');
        const groups = await response.json();
        const group = groups.find(g => g.id === groupId);
        if (!group) return;
        
        document.getElementById('editGroupId').value = group.id;
        document.getElementById('editGroupName').value = group.name;
        document.getElementById('editDurationMinutes').value = group.duration_minutes || 60;
        document.getElementById('editLateThreshold').value = group.late_threshold;
        document.getElementById('editMaxStudents').value = group.max_students || '';
        document.getElementById('editNotes').value = group.notes || '';
        refreshTrainerSelects(group);
        
        // Загружаем выбранные слоты
        editSelectedSlots = [];
        const days = group.schedule_days || [];
        let scheduleTime = group.schedule_time;
        
        console.log('📥 Загрузка группы для редактирования:', group);
        console.log('schedule_time из БД:', scheduleTime);
        console.log('schedule_days из БД:', days);
        
        // Проверяем, является ли schedule_time JSON
        try {
            const timeMap = JSON.parse(scheduleTime);
            console.log('✅ schedule_time - это JSON:', timeMap);
            // Если JSON, то у каждого дня свое время
            days.forEach(day => {
                const time = timeMap[day.toString()];
                if (time) {
                    editSelectedSlots.push({ day: parseInt(day), time });
                }
            });
        } catch {
            console.log('✅ schedule_time - это строка HH:MM');
            // Если не JSON, то все дни имеют одно время
            days.forEach(day => {
                editSelectedSlots.push({ day: parseInt(day), time: scheduleTime });
            });
        }
        
        console.log('📋 Восстановленные слоты:', editSelectedSlots);
        
        updateEditHiddenFields();
        updateEditSelectedSlotsDisplay();
        renderEditScheduleVisualization();
        
        // Загружаем блоки стадиона
        const indices = Array.isArray(group.field_block_indices) && group.field_block_indices.length
            ? group.field_block_indices.slice().sort((a, b) => a - b)
            : Array.from({ length: group.field_blocks || 0 }, (_, i) => i);
        editSelectedFieldBlocks = indices;
        document.getElementById('editFieldBlocks').value = editSelectedFieldBlocks.length;
        renderEditFieldBlocks();
        updateEditFieldBlocksInfo();
        
        document.getElementById('editSlotValidationMessage').style.display = 'none';
        document.getElementById('editGroupModal').style.display = 'block';
    } catch (error) {
        console.error('Ошибка:', error);
    }
}

function closeEditGroupModal() {
    document.getElementById('editGroupModal').style.display = 'none';
    document.getElementById('editGroupForm').reset();
    editSelectedSlots = [];
    editSelectedFieldBlocks = [];
    updateEditSelectedSlotsDisplay();
    document.getElementById('editSlotValidationMessage').style.display = 'none';
}

document.getElementById('editGroupForm').addEventListener('submit', async (e) => {
    e.preventDefault();
    console.log('🔍 Отправка формы редактирования группы...');
    console.log('Edit selected slots:', editSelectedSlots);
    console.log('Edit selected field blocks:', editSelectedFieldBlocks);
    
    const alertBox = document.getElementById('editSlotValidationMessage');
    alertBox.style.display = 'none';
    
    if (editSelectedSlots.length === 0) {
        console.log('❌ Не выбраны слоты расписания');
        alertBox.textContent = 'Выберите хотя бы один день и время занятий';
        alertBox.style.display = 'block';
        return;
    }

    if (editSelectedFieldBlocks.length === 0) {
        console.log('❌ Не выбраны блоки стадиона');
        alertBox.textContent = 'Выберите хотя бы один блок стадиона';
        alertBox.style.display = 'block';
        return;
    }
    
    const groupId = document.getElementById('editGroupId').value;
    const scheduleTimeValue = document.getElementById('editScheduleTime').value;
    const scheduleDaysValue = document.getElementById('editScheduleDays').value;
    
    const data = {
        name: document.getElementById('editGroupName').value,
        duration_minutes: parseInt(document.getElementById('editDurationMinutes').value),
        field_blocks: editSelectedFieldBlocks.length,
        field_block_indices: editSelectedFieldBlocks,
        schedule_time: scheduleTimeValue,
        late_threshold: document.getElementById('editLateThreshold').value,
        max_students: document.getElementById('editMaxStudents').value || null,
        trainer_ids: getMultiSelectValues('editGroupTrainerIds'),
        assistant_ids: getMultiSelectValues('editGroupAssistantIds'),
        notes: document.getElementById('editNotes').value,
        schedule_days: JSON.parse(scheduleDaysValue)
    };
    
    console.log('📤 Отправляемые данные:', data);
    console.log('schedule_time value:', scheduleTimeValue);
    console.log('schedule_days value:', scheduleDaysValue);
    
    try {
        const response = await fetch(`/api/groups/${groupId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        const result = await response.json();
        if (result.success) {
            alert('✓ Группа обновлена!');
            closeEditGroupModal();
            loadGroups();
        } else {
            alertBox.textContent = result.message;
            alertBox.style.display = 'block';
        }
    } catch (error) {
        console.error('Ошибка:', error);
        alertBox.textContent = 'Ошибка при обновлении группы';
        alertBox.style.display = 'block';
    }
});

async function deleteGroup(groupId, groupName) {
    if (!confirm(`Вы уверены, что хотите удалить группу "${groupName}"?\n\nВнимание: Все ученики этой группы будут переведены в состояние "без группы".`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/groups/${groupId}`, {
            method: 'DELETE'
        });
        const result = await response.json();
        
        if (result.success) {
            alert('✓ Группа удалена!');
            loadGroups();
        } else {
            alert('Ошибка: ' + result.message);
        }
    } catch (error) {
        console.error('Ошибка при удалении группы:', error);
        alert('Ошибка при удалении группы');
    }
}

window.onclick = function(event) {
    const addModal = document.getElementById('addGroupModal');
    const editModal = document.getElementById('editGroupModal');
    const settingsModal = document.getElementById('clubSettingsModal');
    if (event.target === addModal) {
        closeAddGroupModal();
    }
    if (event.target === editModal) {
        closeEditGroupModal();
    }
    if (event.target === settingsModal) {
        closeSettingsModal();
    }
};

function showSettingsModal() {
    setWeekdaySelection('settings', clubSettings.working_days || []);
    document.getElementById('settingsStatus').style.display = 'none';
    document.getElementById('clubSettingsModal').style.display = 'block';
}

function closeSettingsModal() {
    document.getElementById('clubSettingsModal').style.display = 'none';
}

const clubSettingsForm = document.getElementById('clubSettingsForm');
if (clubSettingsForm) {
clubSettingsForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const statusBox = document.getElementById('settingsStatus');
    statusBox.style.display = 'none';
    const payload = {
        working_days: getSelectedDays('settings'),
        work_start_time: document.getElementById('workStartTime').value,
        work_end_time: document.getElementById('workEndTime').value,
        max_groups_per_slot: document.getElementById('maxGroupsPerSlot').value,
        block_future_payments: document.getElementById('blockFuturePayments').checked
    };
    if (!payload.working_days.length) {
        statusBox.textContent = 'Выберите рабочие дни';
        statusBox.style.display = 'block';
        return;
    }
    try {
        const response = await fetch('/api/club-settings', {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const result = await response.json();
        if (result.success) {
            alert('Настройки сохранены');
            closeSettingsModal();
            await loadClubSettings();
        } else {
            statusBox.textContent = result.message;
            statusBox.style.display = 'block';
        }
    } catch (error) {
        console.error('Ошибка сохранения настроек:', error);
        statusBox.textContent = 'Ошибка при сохранении настроек';
        statusBox.style.display = 'block';
    }
});
}

// === FIELD BLOCKS VISUALIZATION ===

// Возвращает множество занятых индексов блоков для указанного дня/времени
function getOccupiedBlockIndicesForSlot(day, time, excludeGroupId = null, useEditDuration = false) {
    if (!allGroups) return new Set();

    const durationInputId = useEditDuration ? 'editDurationMinutes' : 'durationMinutes';
    const currentDuration = parseInt(document.getElementById(durationInputId)?.value) || 60;
    const slotStart = parseTime(time);
    const slotEnd = addMinutes(slotStart, currentDuration);

    const occupied = new Set();

    allGroups.forEach(group => {
        if (excludeGroupId && group.id === excludeGroupId) return;

        const groupDays = group.schedule_days || [];
        if (!groupDays.includes(day)) return;

        const groupDuration = group.duration_minutes || 60;
        const groupStart = parseTime(group.schedule_time);
        const groupEnd = addMinutes(groupStart, groupDuration);

        // Пересечение интервалов по времени
        if (groupStart < slotEnd && groupEnd > slotStart) {
            // Берём конкретные индексы блоков, если они есть, иначе первые N блоков
            let indices = group.field_block_indices;
            if (!Array.isArray(indices) || indices.length === 0) {
                const count = group.field_blocks || 0;
                indices = Array.from({ length: count }, (_, i) => i);
            }
            indices.forEach(idx => occupied.add(idx));
        }
    });

    return occupied;
}

function selectFieldBlock(blockIndex) {
    // Проверяем, уже ли выбран этот блок
    const alreadySelected = selectedFieldBlocks.includes(blockIndex);
    
    if (alreadySelected) {
        // Убираем блок из выбранных
        selectedFieldBlocks = selectedFieldBlocks.filter(b => b !== blockIndex);
    } else {
        // Проверяем, можно ли добавить блок (должны быть соседними)
        if (selectedFieldBlocks.length > 0) {
            const min = Math.min(...selectedFieldBlocks);
            const max = Math.max(...selectedFieldBlocks);
            
            // Блок должен быть соседним
            if (blockIndex !== min - 1 && blockIndex !== max + 1) {
                alert('Выбирайте только соседние блоки подряд!');
                return;
            }
        }
        
        // Добавляем блок
        selectedFieldBlocks.push(blockIndex);
        selectedFieldBlocks.sort((a, b) => a - b);
    }
    
    // Обновляем скрытое поле
    document.getElementById('fieldBlocks').value = selectedFieldBlocks.length;
    
    // Обновляем визуализацию
    renderFieldBlocks();
    updateFieldBlocksInfo();
}

function renderFieldBlocks() {
    const container = document.getElementById('fieldBlocksVisualization');
    if (!clubSettings) {
        console.log('⚠️ clubSettings не загружены');
        container.innerHTML = '<div class="field-loading">Загрузка схемы поля...</div>';
        return;
    }
    
    console.log('🏟️ Рендеринг блоков стадиона, max_groups_per_slot:', clubSettings.max_groups_per_slot);
    const totalBlocks = clubSettings.max_groups_per_slot || 4; // Фолбэк если не задано
    if (totalBlocks === 0) {
        console.log('⚠️ totalBlocks = 0, используем дефолт 4');
    }
    const occupiedIndices = getOccupiedBlocksForCurrentSlot();
    
    let html = '<div class="field-stadium">';
    html += '<div class="field-title">⚽ Футбольное поле</div>';
    html += '<div class="field-blocks-grid">';
    
    for (let i = 0; i < totalBlocks; i++) {
        const isSelected = selectedFieldBlocks.includes(i);
        const isOccupied = occupiedIndices.has(i) && !isSelected;
        
        let blockClass = 'field-block';
        let blockText = '';
        let clickHandler = '';
        
        if (isSelected) {
            blockClass += ' selected';
            blockText = '✓';
            clickHandler = `onclick="selectFieldBlock(${i})"`;
        } else if (isOccupied) {
            blockClass += ' occupied';
            blockText = 'Занято';
        } else {
            blockText = 'Свободно';
            clickHandler = `onclick="selectFieldBlock(${i})"`;
        }
        
        html += `
            <div class="${blockClass}" ${clickHandler}>
                <div class="field-block-number">${i + 1}</div>
                <span>${blockText}</span>
            </div>
        `;
    }
    
    html += '</div>';
    
    // Легенда
    html += `
        <div class="field-legend">
            <div class="field-legend-item">
                <div class="field-legend-box available"></div>
                <span>Свободно</span>
            </div>
            <div class="field-legend-item">
                <div class="field-legend-box selected"></div>
                <span>Выбрано</span>
            </div>
            <div class="field-legend-item">
                <div class="field-legend-box occupied"></div>
                <span>Занято</span>
            </div>
        </div>
    `;
    
    html += '</div>';
    container.innerHTML = html;
}

function updateFieldBlocksInfo() {
    const info = document.getElementById('fieldBlocksInfo');
    const selectedCount = document.getElementById('selectedBlocksCount');
    const availableCount = document.getElementById('availableBlocksCount');
    
    if (!clubSettings) return;
    
    const totalBlocks = clubSettings.max_groups_per_slot;
    const occupiedIndices = getOccupiedBlocksForCurrentSlot();
    const availableBlocks = totalBlocks - occupiedIndices.size;
    
    selectedCount.textContent = selectedFieldBlocks.length;
    availableCount.textContent = availableBlocks;
    info.style.display = 'flex';
}

function getOccupiedBlocksForCurrentSlot() {
    if (selectedSlots.length === 0) return new Set();

    const result = new Set();

    selectedSlots.forEach(slot => {
        const occupied = getOccupiedBlockIndicesForSlot(slot.day, slot.time);
        occupied.forEach(idx => result.add(idx));
    });

    return result;
}

// Для окна редактирования
function selectEditFieldBlock(blockIndex) {
    const maxBlocks = clubSettings.max_groups_per_slot;
    
    const alreadySelected = editSelectedFieldBlocks.includes(blockIndex);
    
    if (alreadySelected) {
        editSelectedFieldBlocks = editSelectedFieldBlocks.filter(b => b !== blockIndex);
    } else {
        if (editSelectedFieldBlocks.length > 0) {
            const min = Math.min(...editSelectedFieldBlocks);
            const max = Math.max(...editSelectedFieldBlocks);
            
            if (blockIndex !== min - 1 && blockIndex !== max + 1) {
                alert('Выбирайте только соседние блоки подряд!');
                return;
            }
        }
        
        editSelectedFieldBlocks.push(blockIndex);
        editSelectedFieldBlocks.sort((a, b) => a - b);
    }
    
    document.getElementById('editFieldBlocks').value = editSelectedFieldBlocks.length;
    renderEditFieldBlocks();
    updateEditFieldBlocksInfo();
}

function renderEditFieldBlocks() {
    const container = document.getElementById('editFieldBlocksVisualization');
    if (!clubSettings) {
        console.log('⚠️ clubSettings не загружены (edit)');
        container.innerHTML = '<div class="field-loading">Загрузка схемы поля...</div>';
        return;
    }
    
    console.log('🏟️ Рендеринг блоков стадиона для редактирования, max_groups_per_slot:', clubSettings.max_groups_per_slot);
    const totalBlocks = clubSettings.max_groups_per_slot || 4;
    const editGroupId = parseInt(document.getElementById('editGroupId').value);
    const occupiedIndices = getOccupiedBlocksForEditSlot(editGroupId);
    
    let html = '<div class="field-stadium">';
    html += '<div class="field-title">⚽ Футбольное поле</div>';
    html += '<div class="field-blocks-grid">';
    
    for (let i = 0; i < totalBlocks; i++) {
        const isSelected = editSelectedFieldBlocks.includes(i);
        const isOccupied = occupiedIndices.has(i) && !isSelected;
        
        let blockClass = 'field-block';
        let blockText = '';
        let clickHandler = '';
        
        if (isSelected) {
            blockClass += ' selected';
            blockText = '✓';
            clickHandler = `onclick="selectEditFieldBlock(${i})"`;
        } else if (isOccupied) {
            blockClass += ' occupied';
            blockText = 'Занято';
        } else {
            blockText = 'Свободно';
            clickHandler = `onclick="selectEditFieldBlock(${i})"`;
        }
        
        html += `
            <div class="${blockClass}" ${clickHandler}>
                <div class="field-block-number">${i + 1}</div>
                <span>${blockText}</span>
            </div>
        `;
    }
    
    html += '</div>';
    
    html += `
        <div class="field-legend">
            <div class="field-legend-item">
                <div class="field-legend-box available"></div>
                <span>Свободно</span>
            </div>
            <div class="field-legend-item">
                <div class="field-legend-box selected"></div>
                <span>Выбрано</span>
            </div>
            <div class="field-legend-item">
                <div class="field-legend-box occupied"></div>
                <span>Занято</span>
            </div>
        </div>
    `;
    
    html += '</div>';
    container.innerHTML = html;
}

function updateEditFieldBlocksInfo() {
    const info = document.getElementById('editFieldBlocksInfo');
    const selectedCount = document.getElementById('editSelectedBlocksCount');
    const availableCount = document.getElementById('editAvailableBlocksCount');
    
    if (!clubSettings) return;
    
    const editGroupId = parseInt(document.getElementById('editGroupId').value);
    const totalBlocks = clubSettings.max_groups_per_slot;
    const occupiedIndices = getOccupiedBlocksForEditSlot(editGroupId);
    const availableBlocks = totalBlocks - occupiedIndices.size;
    
    selectedCount.textContent = editSelectedFieldBlocks.length;
    availableCount.textContent = availableBlocks;
    info.style.display = 'flex';
}

function getOccupiedBlocksForEditSlot(excludeGroupId) {
    if (editSelectedSlots.length === 0) return new Set();

    const result = new Set();

    editSelectedSlots.forEach(slot => {
        const occupied = getOccupiedBlockIndicesForSlot(slot.day, slot.time, excludeGroupId, true);
        occupied.forEach(idx => result.add(idx));
    });

    return result;
}

async function sendGroupNotification(groupId, groupName) {
    if (!confirm(`Отправить уведомления всем ученикам группы "${groupName}"?`)) {
        return;
    }
    
    try {
        const response = await fetch(`/api/groups/${groupId}/send-notification`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({})
        });
        
        const result = await response.json();
        
        if (result.success) {
            if (result.success_count > 0) {
                alert(`✅ Уведомления отправлены!\n\nОтправлено: ${result.success_count} из ${result.success_count + result.failed_count}\n${result.failed_count > 0 ? `Не удалось: ${result.failed_count}` : ''}`);
            } else {
                alert(result.message || 'Нет учеников с привязанным Telegram в этой группе');
            }
        } else {
            alert('Ошибка: ' + (result.message || 'Не удалось отправить уведомления'));
        }
    } catch (error) {
        console.error('Ошибка при отправке уведомлений:', error);
        alert('Ошибка при отправке уведомлений: ' + error.message);
    }
}

// На странице настроек группы грузятся при первом открытии вкладки, а не вместе со всей страницей.
let groupsPageLoad = null;
window.ensureGroupsLoaded = () => {
    if (!groupsPageLoad) groupsPageLoad = Promise.all([loadClubSettings(), loadTrainers()]).then(loadGroups);
    return groupsPageLoad;
};
if (!document.body.classList.contains('settings-page')) window.ensureGroupsLoaded();
