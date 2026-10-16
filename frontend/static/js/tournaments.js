const catalogState = {
    tournaments: [],
    teams: [],
    stadiums: [],
    editingTournamentId: null,
    editingTeamId: null,
    editingMemberId: null,
    editingStadiumId: null,
    activeTeamId: null,
    teamLogoObjectUrl: null,
    trainerPhotoObjectUrl: null,
    memberPhotoObjectUrl: null,
    stadiumPhotoObjectUrl: null,
    stadiumMap: null,
    stadiumMarker: null,
    stadiumReturnToTournament: false,
    shareTeamId: null,
    shareLink: null,
    tournamentLocation: '',
    tournamentAgeGroups: [],
    entriesTournamentId: null,
    entries: [],
    entryAgeGroups: [],
    entryTeamIds: [],
    entryTeamHighlight: -1,
    groups: [],
    groupEntries: [],
    groupAge: '',
    matchAge: '',
    matchBlocks: [],
    playoffMatches: [],
    playoffResults: [],
    playersAge: '',
    playersStats: null,
    playersAwards: [],
    protocol: null,
    protocolEvents: [],
    playoffAge: '',
    age: '',
    overview: null,
    formatDirty: false,
    entryTab: 'entries',
    entryAges: [],
    roster: null,
    rosterTeamId: null,
    rosterDirty: false,
    matchStadiums: [],
    tournamentPosterObjectUrl: null,
    tournamentPosterRemoved: false,
    activeFilterTab: 'tournaments',
    filters: {
        tournaments: { search: '', location: '', age: '' },
        teams: { search: '', trainer: '', minMembers: '' },
        stadiums: { search: '', phone: '' },
    },
};

const byId = (id) => document.getElementById(id);

const AGE_GROUP_MIN_YEAR = 1980;
const ADD_STADIUM_OPTION = '__add_stadium__';

function escapeHtml(value) {
    // Значение подставляется и в текст, и в атрибуты. innerHTML не трогает
    // кавычки, из-за чего название вида «"Джар" спорт комплекс» обрывало
    // value="..." и опция приходила пустой. Экранируем вручную.
    return String(value == null ? '' : value)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function refreshIcons() {
    if (window.lucide) window.lucide.createIcons();
}

async function apiJson(url, options = {}) {
    const requestOptions = { credentials: 'same-origin', ...options };
    if (requestOptions.body && !(requestOptions.body instanceof FormData)) {
        requestOptions.headers = { 'Content-Type': 'application/json', ...(requestOptions.headers || {}) };
    }
    const response = await fetch(url, requestOptions);
    const data = await response.json().catch(() => ({}));
    if (!response.ok || data.success === false) {
        throw new Error(data.message || 'Не удалось выполнить действие');
    }
    return data;
}

function formatDate(value) {
    if (!value) return '—';
    return new Intl.DateTimeFormat('ru-RU', {
        day: '2-digit',
        month: 'short',
        year: 'numeric',
    }).format(new Date(`${value}T00:00:00`));
}

function formatBirthDate(value) {
    if (!value) return '—';
    const [year, month, day] = String(value).split('-');
    return year && month && day ? `${day}.${month}.${year}` : '—';
}

function isoToDisplayDate(value) {
    if (!value) return '';
    const [year, month, day] = String(value).split('-');
    return year && month && day ? `${day}.${month}.${year}` : '';
}

function pluralizeMembers(count) {
    const mod10 = count % 10;
    const mod100 = count % 100;
    if (mod10 === 1 && mod100 !== 11) return `${count} участник`;
    if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return `${count} участника`;
    return `${count} участников`;
}

function pluralizeTeams(count) {
    const mod10 = count % 10;
    const mod100 = count % 100;
    if (mod10 === 1 && mod100 !== 11) return `${count} команда`;
    if ([2, 3, 4].includes(mod10) && ![12, 13, 14].includes(mod100)) return `${count} команды`;
    return `${count} команд`;
}

function tournamentDates(item) {
    const start = formatDate(item.start_date);
    const end = formatDate(item.end_date);
    return item.start_date === item.end_date ? start : `${start} — ${end}`;
}

function initials(name) {
    return String(name || '?')
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((part) => part[0])
        .join('')
        .toUpperCase();
}

function normalizeSearch(value) {
    return String(value || '').trim().toLocaleLowerCase('ru-RU');
}

function includesSearch(value, query) {
    return !query || normalizeSearch(value).includes(normalizeSearch(query));
}

function filteredTournaments() {
    const filter = catalogState.filters.tournaments;
    return catalogState.tournaments.filter((item) => {
        const searchable = [
            item.name,
            item.location,
            item.start_date,
            item.end_date,
            item.start_time,
            ...(item.age_groups || []),
        ].join(' ');
        return includesSearch(searchable, filter.search)
            && includesSearch(item.location, filter.location)
            && includesSearch((item.age_groups || []).join(' '), filter.age);
    });
}

function filteredTeams() {
    const filter = catalogState.filters.teams;
    const minimumMembers = filter.minMembers === '' ? null : Number(filter.minMembers);
    return catalogState.teams.filter((team) => {
        const searchable = [
            team.name,
            team.trainer_name,
            team.trainer_phone,
            team.administration_phone,
            team.club_address,
        ].join(' ');
        return includesSearch(searchable, filter.search)
            && includesSearch(team.trainer_name, filter.trainer)
            && (minimumMembers === null || (Number(team.member_count) || 0) >= minimumMembers);
    });
}

function filteredStadiums() {
    const filter = catalogState.filters.stadiums;
    return catalogState.stadiums.filter((stadium) => {
        const searchable = [
            stadium.name,
            stadium.owner_phone,
            stadium.length,
            stadium.width,
            stadium.latitude,
            stadium.longitude,
        ].join(' ');
        return includesSearch(searchable, filter.search)
            && includesSearch(stadium.owner_phone, filter.phone);
    });
}

function setCatalogCount(id, visibleCount, totalCount) {
    byId(id).textContent = visibleCount === totalCount
        ? String(totalCount)
        : `${visibleCount}/${totalCount}`;
}

function emptyCatalogMarkup(icon, title, description) {
    return `
        <div class="tournament-catalog-empty">
            <i data-lucide="${icon}"></i>
            <strong>${escapeHtml(title)}</strong>
            <span>${escapeHtml(description)}</span>
        </div>`;
}

function renderTournaments() {
    const items = filteredTournaments();
    setCatalogCount('tournamentCount', items.length, catalogState.tournaments.length);
    if (!items.length) {
        byId('tournamentList').innerHTML = emptyCatalogMarkup(
            'trophy',
            catalogState.tournaments.length ? 'Ничего не найдено' : 'Турниров пока нет',
            catalogState.tournaments.length
                ? 'Измените поисковый запрос или сбросьте фильтры.'
                : 'Создайте первый турнир, указав дату, время, возраст и локацию.',
        );
        refreshIcons();
        return;
    }
    byId('tournamentList').innerHTML = `
        <div class="catalog-table-wrap">
            <table class="catalog-data-table tournament-catalog-table">
                <thead>
                    <tr>
                        <th>Турнир</th>
                        <th>Дата проведения</th>
                        <th>Время</th>
                        <th>Локация</th>
                        <th>Возрастные группы</th>
                        <th aria-label="Действия"></th>
                    </tr>
                </thead>
                <tbody>
                    ${items.map((item) => `
                        <tr class="tournament-row" data-row-tournament="${item.id}" title="Открыть турнир">
                            <td data-label="Турнир">
                                <button class="team-table-team" type="button" data-open-tournament="${item.id}">
                                    <span class="catalog-row-icon"><i data-lucide="trophy"></i></span>
                                    <span class="team-table-name">
                                        <strong>${escapeHtml(item.name)}</strong>
                                        <small>Открыть турнир</small>
                                    </span>
                                </button>
                            </td>
                            <td data-label="Дата">${escapeHtml(tournamentDates(item))}</td>
                            <td data-label="Время">${escapeHtml(item.start_time || '—')}</td>
                            <td data-label="Локация">${escapeHtml(item.location || '—')}</td>
                            <td data-label="Возраст">
                                <span class="catalog-age-list">
                                    ${(item.age_groups || []).length
                                        ? item.age_groups.map((group) => `<span>${escapeHtml(group)}</span>`).join('')
                                        : '—'}
                                </span>
                            </td>
                            <td class="catalog-actions-cell">
                                <details class="team-actions-menu">
                                    <summary class="icon-button" aria-label="Действия с турниром">
                                        <i data-lucide="ellipsis-vertical"></i>
                                    </summary>
                                    <div class="team-actions-popover">
                                        <button class="catalog-menu-action" type="button" data-entries-tournament="${item.id}">
                                            <i data-lucide="users-round"></i>
                                            Участники
                                        </button>
                                        <button class="catalog-menu-action" type="button" data-edit-tournament="${item.id}">
                                            <i data-lucide="pencil"></i>
                                            Редактировать
                                        </button>
                                        <button class="catalog-menu-action danger" type="button" data-delete-tournament="${item.id}">
                                            <i data-lucide="trash-2"></i>
                                            Удалить
                                        </button>
                                    </div>
                                </details>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>`;
    refreshIcons();
}

function renderTeams() {
    const teams = filteredTeams();
    setCatalogCount('teamCount', teams.length, catalogState.teams.length);
    if (!teams.length) {
        byId('teamList').innerHTML = emptyCatalogMarkup(
            'shield',
            catalogState.teams.length ? 'Ничего не найдено' : 'Команд пока нет',
            catalogState.teams.length
                ? 'Измените поисковый запрос или сбросьте фильтры.'
                : 'Добавьте название и логотип первой команды.',
        );
        refreshIcons();
        return;
    }
    byId('teamList').innerHTML = `
        <div class="team-catalog-table-wrap">
            <table class="catalog-data-table team-catalog-table">
                <thead>
                    <tr>
                        <th>Команда</th>
                        <th>Тренер</th>
                        <th>Контакты</th>
                        <th>Участники</th>
                        <th aria-label="Действия"></th>
                    </tr>
                </thead>
                <tbody>
                    ${teams.map((team) => `
                        <tr>
                            <td data-label="Команда">
                                <button class="team-table-team" type="button" data-open-team="${team.id}">
                                    <span class="team-table-logo">
                                        ${team.logo_url
                                            ? `<img src="${escapeHtml(team.logo_url)}" alt="">`
                                            : `<span>${escapeHtml(initials(team.name))}</span>`}
                                    </span>
                                    <span class="team-table-name">
                                        <strong>${escapeHtml(team.name)}</strong>
                                        <small>Открыть состав</small>
                                    </span>
                                </button>
                            </td>
                            <td data-label="Тренер">
                                <span class="team-table-value">${escapeHtml(team.trainer_name || '—')}</span>
                            </td>
                            <td data-label="Контакты">
                                <span class="team-table-contacts">
                                    ${team.trainer_phone || team.administration_phone
                                        ? `<span>${escapeHtml(team.trainer_phone || team.administration_phone)}</span>`
                                        : '<span>—</span>'}
                                    ${team.club_address ? `<small>${escapeHtml(team.club_address)}</small>` : ''}
                                </span>
                            </td>
                            <td data-label="Участники">
                                <span class="team-table-members">
                                    <i data-lucide="users-round"></i>
                                    ${escapeHtml(pluralizeMembers(Number(team.member_count) || 0))}
                                </span>
                            </td>
                            <td class="team-table-actions">
                                <details class="team-actions-menu">
                                    <summary class="icon-button" aria-label="Действия с командой">
                                        <i data-lucide="ellipsis-vertical"></i>
                                    </summary>
                                    <div class="team-actions-popover">
                                        <button class="catalog-menu-action" type="button" data-share-team="${team.id}">
                                            <i data-lucide="share-2"></i>
                                            Поделиться
                                        </button>
                                        <button class="catalog-menu-action" type="button" data-edit-team="${team.id}">
                                            <i data-lucide="pencil"></i>
                                            Редактировать
                                        </button>
                                        <button class="catalog-menu-action danger" type="button" data-delete-team="${team.id}">
                                            <i data-lucide="trash-2"></i>
                                            Удалить
                                        </button>
                                    </div>
                                </details>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>`;
    refreshIcons();
}

function renderStadiums() {
    const stadiums = filteredStadiums();
    setCatalogCount('stadiumCount', stadiums.length, catalogState.stadiums.length);
    if (!stadiums.length) {
        byId('stadiumList').innerHTML = emptyCatalogMarkup(
            'map-pinned',
            catalogState.stadiums.length ? 'Ничего не найдено' : 'Стадионов пока нет',
            catalogState.stadiums.length
                ? 'Измените поисковый запрос или сбросьте фильтры.'
                : 'Добавьте стадион и отметьте его точку на карте.',
        );
        refreshIcons();
        return;
    }
    byId('stadiumList').innerHTML = `
        <div class="catalog-table-wrap">
            <table class="catalog-data-table stadium-catalog-table">
                <thead>
                    <tr>
                        <th>Стадион</th>
                        <th>Телефон владельца</th>
                        <th>Размер поля</th>
                        <th>Координаты</th>
                        <th>Локация</th>
                        <th aria-label="Действия"></th>
                    </tr>
                </thead>
                <tbody>
                    ${stadiums.map((stadium) => `
                        <tr>
                            <td data-label="Стадион">
                                <span class="catalog-primary-cell">
                                    <span class="catalog-row-icon catalog-stadium-photo">
                                        ${stadium.photo_url
                                            ? `<img src="${escapeHtml(stadium.photo_url)}" alt="">`
                                            : '<i data-lucide="map-pin"></i>'}
                                    </span>
                                    <span class="catalog-stadium-name">
                                        <strong>${escapeHtml(stadium.name)}</strong>
                                        ${stadium.photo_source
                                            ? `<small class="stadium-photo-credit">Фото: ${escapeHtml(stadium.photo_source)}</small>`
                                            : ''}
                                    </span>
                                </span>
                            </td>
                            <td data-label="Телефон">${escapeHtml(stadium.owner_phone || '—')}</td>
                            <td data-label="Размер">
                                ${stadium.length && stadium.width
                                    ? `${escapeHtml(stadium.length)} × ${escapeHtml(stadium.width)} м`
                                    : stadium.length
                                        ? `${escapeHtml(stadium.length)} м (длина)`
                                        : stadium.width
                                            ? `${escapeHtml(stadium.width)} м (ширина)`
                                            : '—'}
                            </td>
                            <td data-label="Координаты">
                                ${Number(stadium.latitude).toFixed(6)}, ${Number(stadium.longitude).toFixed(6)}
                            </td>
                            <td data-label="Локация">
                                <a class="catalog-map-link" href="https://www.openstreetmap.org/?mlat=${encodeURIComponent(stadium.latitude)}&mlon=${encodeURIComponent(stadium.longitude)}#map=17/${encodeURIComponent(stadium.latitude)}/${encodeURIComponent(stadium.longitude)}"
                                    target="_blank" rel="noopener">
                                    <i data-lucide="map"></i>
                                    На карте
                                </a>
                            </td>
                            <td class="catalog-actions-cell">
                                <details class="team-actions-menu">
                                    <summary class="icon-button" aria-label="Действия со стадионом">
                                        <i data-lucide="ellipsis-vertical"></i>
                                    </summary>
                                    <div class="team-actions-popover">
                                        <button class="catalog-menu-action" type="button" data-edit-stadium="${stadium.id}">
                                            <i data-lucide="pencil"></i>
                                            Редактировать
                                        </button>
                                        <button class="catalog-menu-action danger" type="button" data-delete-stadium="${stadium.id}">
                                            <i data-lucide="trash-2"></i>
                                            Удалить
                                        </button>
                                    </div>
                                </details>
                            </td>
                        </tr>
                    `).join('')}
                </tbody>
            </table>
        </div>`;
    refreshIcons();
}

async function loadTournaments() {
    const data = await apiJson('/api/tournaments');
    catalogState.tournaments = data.tournaments || [];
    renderTournaments();
}

async function loadTeams() {
    const data = await apiJson('/api/tournament-team-catalog');
    catalogState.teams = data.teams || [];
    renderTeams();
}

async function loadStadiums() {
    const data = await apiJson('/api/tournament-stadiums');
    catalogState.stadiums = data.stadiums || [];
    renderStadiums();
    renderStadiumOptions();
}

function openModal(id) {
    const modal = byId(id);
    modal.hidden = false;
    document.body.classList.add('modal-open');
    refreshIcons();
}

function closeModal(id) {
    byId(id).hidden = true;
    if (id === 'rosterModal') byId(id).dispatchEvent(new Event('roster:closed'));
    if (id === 'stadiumModal') catalogState.stadiumReturnToTournament = false;
    if (!document.querySelector('.tournament-catalog-modal:not([hidden])')) {
        document.body.classList.remove('modal-open');
    }
}

function showFormError(id, message = '') {
    const element = byId(id);
    element.textContent = message;
    element.hidden = !message;
}

/* --- Локация: выпадающий список стадионов с быстрым добавлением --- */

function renderStadiumOptions(selectedName) {
    const select = byId('tournamentLocation');
    if (!select) return;
    const current = selectedName !== undefined ? selectedName : catalogState.tournamentLocation;
    const names = catalogState.stadiums.map((item) => item.name).filter(Boolean);
    const options = ['<option value="">Выберите стадион</option>'];
    // Локация турниров, созданных до появления справочника, не должна теряться.
    if (current && !names.includes(current)) {
        options.push(`<option value="${escapeHtml(current)}">${escapeHtml(current)}</option>`);
    }
    names.forEach((name) => {
        options.push(`<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`);
    });
    options.push(`<option value="${ADD_STADIUM_OPTION}">+ Добавить стадион…</option>`);
    select.innerHTML = options.join('');
    select.value = current || '';
    catalogState.tournamentLocation = select.value;
}

function handleTournamentLocationChange(event) {
    const select = event.target;
    if (select.value !== ADD_STADIUM_OPTION) {
        catalogState.tournamentLocation = select.value;
        return;
    }
    // Возвращаем прежний выбор и открываем создание стадиона поверх окна турнира.
    select.value = catalogState.tournamentLocation || '';
    openStadiumCreator({ returnToTournament: true });
}

/* --- Возрастные группы: годы с 1980 по текущий + произвольные значения --- */

function ageGroupYears() {
    const years = [];
    for (let year = new Date().getFullYear(); year >= AGE_GROUP_MIN_YEAR; year -= 1) {
        years.push(year);
    }
    return years;
}

function renderAgeGroupYearOptions() {
    const select = byId('tournamentAgeGroupYear');
    if (!select) return;
    // Список строится при каждом открытии формы, поэтому новый год появляется сам.
    select.innerHTML = ['<option value="">Добавить год…</option>']
        .concat(ageGroupYears().map((year) => `<option value="${year}">${year}</option>`))
        .join('');
}

function renderAgeGroupChips() {
    const container = byId('tournamentAgeGroupChips');
    if (!container) return;
    const values = catalogState.tournamentAgeGroups;
    container.innerHTML = values.length
        ? values.map((value, index) => `
            <span class="age-group-chip">
                ${escapeHtml(value)}
                <button type="button" data-remove-age-group="${index}"
                    aria-label="Убрать ${escapeHtml(value)}">&times;</button>
            </span>
        `).join('')
        : '<span class="age-group-empty">Группы не выбраны</span>';
    byId('tournamentAgeGroups').value = values.join(', ');
}

function setAgeGroups(values) {
    const list = [];
    (values || []).forEach((item) => {
        const label = String(item == null ? '' : item).trim();
        if (label && !list.includes(label)) list.push(label);
    });
    catalogState.tournamentAgeGroups = list;
    renderAgeGroupChips();
}

function addAgeGroup(value) {
    const label = String(value == null ? '' : value).trim();
    if (!label) return;
    if (!catalogState.tournamentAgeGroups.includes(label)) {
        catalogState.tournamentAgeGroups.push(label);
    }
    renderAgeGroupChips();
}

function removeAgeGroup(index) {
    catalogState.tournamentAgeGroups.splice(Number(index), 1);
    renderAgeGroupChips();
}

function addCustomAgeGroup() {
    const input = byId('tournamentAgeGroupCustom');
    // Одной строкой можно добавить сразу несколько групп через запятую.
    String(input.value || '').split(/[,;]+/).forEach(addAgeGroup);
    input.value = '';
}

function setTournamentPoster(url, caption) {
    const box = byId('tournamentPosterPreview');
    if (url) {
        box.innerHTML = '';
        box.style.backgroundImage = `url('${url}')`;
    } else {
        box.style.backgroundImage = '';
        box.innerHTML = '<i data-lucide="image-plus"></i>';
    }
    byId('tournamentPosterHint').textContent = caption || 'Необязательно · нажмите, чтобы выбрать';
    byId('tournamentPosterClear').hidden = !url;
    refreshIcons();
}

function releaseTournamentPoster() {
    if (catalogState.tournamentPosterObjectUrl) {
        URL.revokeObjectURL(catalogState.tournamentPosterObjectUrl);
        catalogState.tournamentPosterObjectUrl = null;
    }
}

function resetTournamentForm() {
    catalogState.editingTournamentId = null;
    byId('tournamentForm').reset();
    byId('tournamentModalTitle').textContent = 'Новый турнир';
    catalogState.tournamentLocation = '';
    catalogState.tournamentPosterRemoved = false;
    releaseTournamentPoster();
    byId('tournamentPoster').value = '';
    setTournamentPoster('');
    byId('tournamentPublished').checked = true;
    renderStadiumOptions('');
    renderAgeGroupYearOptions();
    setAgeGroups([]);
    byId('tournamentAgeGroupCustom').value = '';
    showFormError('tournamentFormError');
}

function openTournamentEditor(id) {
    const item = catalogState.tournaments.find((row) => Number(row.id) === Number(id));
    if (!item) return;
    catalogState.editingTournamentId = item.id;
    byId('tournamentModalTitle').textContent = 'Редактировать турнир';
    byId('tournamentName').value = item.name || '';
    byId('tournamentStartDate').value = item.start_date || '';
    byId('tournamentStartTime').value = item.start_time || '';
    byId('tournamentEndDate').value = item.end_date || '';
    byId('tournamentPublished').checked = item.is_published !== false;
    catalogState.tournamentPosterRemoved = false;
    releaseTournamentPoster();
    byId('tournamentPoster').value = '';
    setTournamentPoster(item.poster_url || '',
        item.poster_url ? 'Текущая афиша · нажмите, чтобы заменить' : '');
    renderStadiumOptions(item.location || '');
    renderAgeGroupYearOptions();
    setAgeGroups(item.age_groups || []);
    byId('tournamentAgeGroupCustom').value = '';
    showFormError('tournamentFormError');
    openModal('tournamentModal');
}

async function saveTournament(event) {
    event.preventDefault();
    const editingId = catalogState.editingTournamentId;
    try {
        showFormError('tournamentFormError');
        // Скрытое поле не участвует в проверке браузера — валидируем вручную.
        if (!catalogState.tournamentAgeGroups.length) {
            showFormError('tournamentFormError', 'Добавьте хотя бы одну возрастную группу');
            return;
        }
        // FormData, а не JSON: вместе с полями уходит файл афиши.
        const payload = new FormData();
        payload.append('name', byId('tournamentName').value);
        payload.append('start_date', byId('tournamentStartDate').value);
        payload.append('start_time', byId('tournamentStartTime').value);
        payload.append('end_date', byId('tournamentEndDate').value);
        payload.append('location', byId('tournamentLocation').value);
        payload.append('age_groups', byId('tournamentAgeGroups').value);
        payload.append('is_published', byId('tournamentPublished').checked ? 'true' : 'false');
        const posterFile = byId('tournamentPoster').files[0];
        if (posterFile) payload.append('poster', posterFile);
        if (catalogState.tournamentPosterRemoved) payload.append('remove_poster', 'true');
        await apiJson(editingId ? `/api/tournaments/${editingId}` : '/api/tournaments', {
            method: editingId ? 'PUT' : 'POST',
            body: payload,
        });
        closeModal('tournamentModal');
        resetTournamentForm();
        await loadTournaments();
    } catch (error) {
        showFormError('tournamentFormError', error.message);
    }
}

async function deleteTournament(id) {
    const item = catalogState.tournaments.find((row) => Number(row.id) === Number(id));
    if (!item || !window.confirm(`Удалить турнир «${item.name}»?`)) return;
    await apiJson(`/api/tournaments/${id}`, { method: 'DELETE' });
    await loadTournaments();
}

function releaseTeamLogoPreview() {
    if (catalogState.teamLogoObjectUrl) {
        URL.revokeObjectURL(catalogState.teamLogoObjectUrl);
        catalogState.teamLogoObjectUrl = null;
    }
}

function releaseObjectUrl(stateKey) {
    if (catalogState[stateKey]) {
        URL.revokeObjectURL(catalogState[stateKey]);
        catalogState[stateKey] = null;
    }
}

function setTeamLogoPreview(url = '', fileName = 'PNG, JPG или WEBP') {
    releaseTeamLogoPreview();
    byId('teamLogoPreview').innerHTML = url
        ? `<img src="${escapeHtml(url)}" alt="">`
        : '<i data-lucide="image-plus"></i>';
    byId('teamLogoFileName').textContent = fileName;
    refreshIcons();
}

function setPhotoPreview(previewId, fileNameId, url = '', fallbackIcon = 'user-round', fileName = 'PNG, JPG или WEBP') {
    byId(previewId).innerHTML = url
        ? `<img src="${escapeHtml(url)}" alt="">`
        : `<i data-lucide="${fallbackIcon}"></i>`;
    byId(fileNameId).textContent = fileName;
    refreshIcons();
}

function resetTeamForm() {
    catalogState.editingTeamId = null;
    byId('teamForm').reset();
    byId('teamModalTitle').textContent = 'Новая команда';
    setTeamLogoPreview();
    releaseObjectUrl('trainerPhotoObjectUrl');
    setPhotoPreview(
        'trainerPhotoPreview',
        'trainerPhotoFileName',
        '',
        'user-round',
        'Необязательно · PNG, JPG или WEBP',
    );
    showFormError('teamFormError');
}

function openTeamEditor(id) {
    const team = catalogState.teams.find((row) => Number(row.id) === Number(id));
    if (!team) return;
    catalogState.editingTeamId = team.id;
    byId('teamModalTitle').textContent = 'Редактировать команду';
    byId('teamName').value = team.name || '';
    byId('teamTrainerName').value = team.trainer_name || '';
    byId('teamAdministrationPhone').value = team.administration_phone || '';
    byId('teamTrainerPhone').value = team.trainer_phone || '';
    byId('teamClubAddress').value = team.club_address || '';
    setTeamLogoPreview(team.logo_url || '', team.logo_url ? 'Текущий логотип' : 'PNG, JPG или WEBP');
    setPhotoPreview(
        'trainerPhotoPreview',
        'trainerPhotoFileName',
        team.trainer_photo_url || '',
        'user-round',
        team.trainer_photo_url ? 'Текущее фото тренера' : 'Необязательно · PNG, JPG или WEBP',
    );
    showFormError('teamFormError');
    openModal('teamModal');
}

async function saveTeam(event) {
    event.preventDefault();
    const editingId = catalogState.editingTeamId;
    const logo = byId('teamLogo').files[0];
    if (!editingId && !logo) {
        showFormError('teamFormError', 'Добавьте логотип команды');
        return;
    }
    const formData = new FormData();
    formData.append('name', byId('teamName').value);
    formData.append('trainer_name', byId('teamTrainerName').value);
    formData.append('administration_phone', byId('teamAdministrationPhone').value);
    formData.append('trainer_phone', byId('teamTrainerPhone').value);
    formData.append('club_address', byId('teamClubAddress').value);
    if (logo) formData.append('logo', logo);
    const trainerPhoto = byId('teamTrainerPhoto').files[0];
    if (trainerPhoto) formData.append('trainer_photo', trainerPhoto);
    try {
        showFormError('teamFormError');
        await apiJson(editingId ? `/api/tournament-team-catalog/${editingId}` : '/api/tournament-team-catalog', {
            method: editingId ? 'PUT' : 'POST',
            body: formData,
        });
        closeModal('teamModal');
        resetTeamForm();
        await loadTeams();
    } catch (error) {
        showFormError('teamFormError', error.message);
    }
}

async function deleteTeam(id) {
    const team = catalogState.teams.find((row) => Number(row.id) === Number(id));
    if (!team || !window.confirm(`Удалить команду «${team.name}» из базы?`)) return;
    await apiJson(`/api/tournament-team-catalog/${id}`, { method: 'DELETE' });
    await loadTeams();
}

function teamLogoMarkup(team) {
    return team.logo_url
        ? `<img src="${escapeHtml(team.logo_url)}" alt="${escapeHtml(team.name)}">`
        : `<span>${escapeHtml(initials(team.name))}</span>`;
}

function renderTeamDetails(team) {
    catalogState.activeTeamId = team.id;
    byId('teamDetailsTitle').textContent = team.name;
    byId('teamDetailsLogo').innerHTML = teamLogoMarkup(team);
    const contacts = [
        team.trainer_name ? {
            icon: 'user-round',
            label: 'Тренер',
            value: team.trainer_name,
            photo: team.trainer_photo_url,
        } : null,
        team.trainer_phone ? { icon: 'phone', label: 'Телефон тренера', value: team.trainer_phone } : null,
        team.administration_phone ? { icon: 'building-2', label: 'Администрация', value: team.administration_phone } : null,
        team.club_address ? { icon: 'map-pin', label: 'Адрес клуба', value: team.club_address } : null,
    ].filter(Boolean);
    byId('teamContactSummary').innerHTML = contacts.length
        ? contacts.map((item) => `
            <div class="team-contact-item">
                ${item.photo
                    ? `<img src="${escapeHtml(item.photo)}" alt="">`
                    : `<span><i data-lucide="${item.icon}"></i></span>`}
                <div><small>${escapeHtml(item.label)}</small><strong>${escapeHtml(item.value)}</strong></div>
            </div>`).join('')
        : '<div class="team-contact-empty">Контактные данные команды пока не заполнены.</div>';
    const members = team.members || [];
    byId('teamMemberCount').textContent = pluralizeMembers(members.length);
    byId('teamMembersTableBody').innerHTML = members.length
        ? members.map((member) => `
            <tr>
                <td data-label="Участник">
                    <div class="team-member-person">
                        <span class="team-member-avatar">
                            ${member.photo_url
                                ? `<img src="${escapeHtml(member.photo_url)}" alt="">`
                                : escapeHtml(initials(member.full_name))}
                        </span>
                        <div>
                            <strong>${escapeHtml(member.full_name)}</strong>
                            <small>${escapeHtml(member.address || 'Адрес не указан')}</small>
                        </div>
                    </div>
                </td>
                <td data-label="Дата рождения">${escapeHtml(formatBirthDate(member.birth_date))}</td>
                <td data-label="Паспорт">${escapeHtml(member.passport_series || '—')}</td>
                <td data-label="Телефоны">
                    <div class="team-member-phones">
                        <span>${escapeHtml(member.phone_primary || '—')}</span>
                        ${member.phone_secondary ? `<small>${escapeHtml(member.phone_secondary)}</small>` : ''}
                    </div>
                </td>
                <td data-label="Позиция">${escapeHtml(member.position || '—')}</td>
                <td data-label="Номер"><span class="team-number-badge">${escapeHtml(member.team_number || '—')}</span></td>
                <td class="team-member-actions">
                    <button class="icon-button" type="button" data-edit-member="${member.id}" aria-label="Редактировать">
                        <i data-lucide="pencil"></i>
                    </button>
                    <button class="icon-button danger" type="button" data-delete-member="${member.id}" aria-label="Удалить">
                        <i data-lucide="trash-2"></i>
                    </button>
                </td>
            </tr>`).join('')
        : `<tr><td colspan="7"><div class="team-members-empty">
            <i data-lucide="users-round"></i>
            <strong>Участников пока нет</strong>
            <span>Добавьте первого игрока в состав команды.</span>
        </div></td></tr>`;
    refreshIcons();
}

async function openTeamDetails(id) {
    const data = await apiJson(`/api/tournament-team-catalog/${id}`);
    const index = catalogState.teams.findIndex((item) => Number(item.id) === Number(data.team.id));
    if (index >= 0) catalogState.teams[index] = data.team;
    renderTeamDetails(data.team);
    openModal('teamDetailsModal');
}

function resetMemberForm() {
    catalogState.editingMemberId = null;
    byId('memberForm').reset();
    byId('memberModalTitle').textContent = 'Новый участник';
    releaseObjectUrl('memberPhotoObjectUrl');
    setPhotoPreview('memberPhotoPreview', 'memberPhotoFileName', '', 'user-round-plus');
    showFormError('memberFormError');
}

function activeTeamMember(id) {
    const team = catalogState.teams.find((item) => Number(item.id) === Number(catalogState.activeTeamId));
    return (team?.members || []).find((item) => Number(item.id) === Number(id));
}

async function getActiveTeam() {
    if (!catalogState.activeTeamId) return null;
    const data = await apiJson(`/api/tournament-team-catalog/${catalogState.activeTeamId}`);
    const index = catalogState.teams.findIndex((item) => Number(item.id) === Number(data.team.id));
    if (index >= 0) catalogState.teams[index] = data.team;
    renderTeamDetails(data.team);
    renderTeams();
    return data.team;
}

async function openMemberEditor(id) {
    let member = activeTeamMember(id);
    if (!member) {
        const team = await getActiveTeam();
        member = (team?.members || []).find((item) => Number(item.id) === Number(id));
    }
    if (!member) return;
    catalogState.editingMemberId = member.id;
    byId('memberModalTitle').textContent = 'Редактировать участника';
    byId('memberLastName').value = member.last_name || '';
    byId('memberFirstName').value = member.first_name || '';
    byId('memberMiddleName').value = member.middle_name || '';
    byId('memberBirthDate').value = isoToDisplayDate(member.birth_date);
    byId('memberPassportSeries').value = member.passport_series || '';
    byId('memberAddress').value = member.address || '';
    byId('memberPhonePrimary').value = member.phone_primary || '';
    byId('memberPhoneSecondary').value = member.phone_secondary || '';
    byId('memberTeamNumber').value = member.team_number || '';
    byId('memberPosition').value = member.position || '';
    setPhotoPreview(
        'memberPhotoPreview',
        'memberPhotoFileName',
        member.photo_url || '',
        'user-round-plus',
        member.photo_url ? 'Текущее фото участника' : 'PNG, JPG или WEBP',
    );
    showFormError('memberFormError');
    openModal('memberModal');
}

async function saveMember(event) {
    event.preventDefault();
    if (!catalogState.activeTeamId) return;
    const formData = new FormData();
    formData.append('last_name', byId('memberLastName').value);
    formData.append('first_name', byId('memberFirstName').value);
    formData.append('middle_name', byId('memberMiddleName').value);
    formData.append('birth_date', byId('memberBirthDate').value);
    formData.append('passport_series', byId('memberPassportSeries').value);
    formData.append('address', byId('memberAddress').value);
    formData.append('phone_primary', byId('memberPhonePrimary').value);
    formData.append('phone_secondary', byId('memberPhoneSecondary').value);
    formData.append('team_number', byId('memberTeamNumber').value);
    formData.append('position', byId('memberPosition').value);
    const photo = byId('memberPhoto').files[0];
    if (photo) formData.append('photo', photo);
    const editingId = catalogState.editingMemberId;
    try {
        showFormError('memberFormError');
        await apiJson(
            editingId
                ? `/api/tournament-team-members/${editingId}`
                : `/api/tournament-team-catalog/${catalogState.activeTeamId}/members`,
            { method: editingId ? 'PUT' : 'POST', body: formData },
        );
        closeModal('memberModal');
        resetMemberForm();
        await getActiveTeam();
    } catch (error) {
        showFormError('memberFormError', error.message);
    }
}

async function deleteMember(id) {
    const member = activeTeamMember(id);
    if (!member || !window.confirm(`Удалить участника «${member.full_name}»?`)) return;
    await apiJson(`/api/tournament-team-members/${id}`, { method: 'DELETE' });
    await getActiveTeam();
}

function setStadiumCoordinates(latitude, longitude) {
    byId('stadiumLatitude').value = Number(latitude).toFixed(7);
    byId('stadiumLongitude').value = Number(longitude).toFixed(7);
    byId('stadiumCoordinates').textContent = `${Number(latitude).toFixed(6)}, ${Number(longitude).toFixed(6)}`;
    if (!catalogState.stadiumMap || !window.L) return;
    const latLng = [Number(latitude), Number(longitude)];
    if (catalogState.stadiumMarker) {
        catalogState.stadiumMarker.setLatLng(latLng);
    } else {
        catalogState.stadiumMarker = L.marker(latLng).addTo(catalogState.stadiumMap);
    }
}

function ensureStadiumMap(latitude = 41.3111, longitude = 69.2797, hasSelection = false) {
    if (!window.L) {
        byId('stadiumMap').innerHTML = '<div class="stadium-map-error">Карта не загрузилась. Проверьте подключение к интернету.</div>';
        return;
    }
    if (!catalogState.stadiumMap) {
        catalogState.stadiumMap = L.map('stadiumMap').setView([latitude, longitude], 12);
        L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
            maxZoom: 19,
            attribution: '&copy; OpenStreetMap',
        }).addTo(catalogState.stadiumMap);
        catalogState.stadiumMap.on('click', (event) => {
            setStadiumCoordinates(event.latlng.lat, event.latlng.lng);
        });
    } else {
        catalogState.stadiumMap.setView([latitude, longitude], hasSelection ? 16 : 12);
    }
    if (catalogState.stadiumMarker) {
        catalogState.stadiumMarker.remove();
        catalogState.stadiumMarker = null;
    }
    if (hasSelection) setStadiumCoordinates(latitude, longitude);
    window.setTimeout(() => catalogState.stadiumMap.invalidateSize(), 80);
}

/* --- Участники турнира: заявки команд по возрастным категориям --- */

const ENTRY_STATUS_ORDER = ['confirmed', 'invited', 'declined'];

function renderEntryTournamentCard(tournament) {
    // Одна строка под названием: всё остальное о турнире есть в списке турниров.
    const parts = [
        tournamentDates(tournament),
        tournament.start_time,
        tournament.location,
        tournament.is_published === false ? 'черновик, на сайте не виден' : 'на сайте',
    ].filter(Boolean);
    byId('entriesTournamentMeta').textContent = parts.join(' · ');
}

function renderEntryRing() {
    const box = byId('entryRing');
    if (!box) return;
    const total = catalogState.entries.length;
    const confirmed = catalogState.entries.filter((item) => item.status === 'confirmed').length;
    const radius = 32;
    const circumference = 2 * Math.PI * radius;
    const filled = total ? (confirmed / total) * circumference : 0;
    const label = `Подтвердили ${confirmed} из ${total}`;

    // Доля от целого: заливка и трек — один тон, число в центре несёт значение.
    box.innerHTML = `
        <svg viewBox="0 0 80 80" role="img" aria-label="${escapeHtml(label)}">
            <title>${escapeHtml(label)}</title>
            <circle cx="40" cy="40" r="${radius}" fill="none" stroke="#ffe4c4" stroke-width="9"></circle>
            <circle cx="40" cy="40" r="${radius}" fill="none" stroke="#ee7800" stroke-width="9"
                stroke-linecap="round" transform="rotate(-90 40 40)"
                stroke-dasharray="${filled} ${circumference}"></circle>
            <text x="40" y="40" text-anchor="middle" dominant-baseline="central"
                class="entry-ring-value">${confirmed}</text>
        </svg>`;
}

function selectedEntryAges() {
    return [...document.querySelectorAll('#entryAgeChips input:checked')].map((input) => input.value);
}

function pickerExcludedIds() {
    const ages = selectedEntryAges();
    // Команду не предлагаем, только если она уже есть во ВСЕХ отмеченных категориях:
    // один клуб может играть сразу в 2010-2011 A, 2010-2011 B и 2012-2013 A.
    const full = new Set(catalogState.teams
        .filter((team) => ages.length && ages.every((age) => catalogState.entries.some((entry) =>
            entry.age_group === age && Number(entry.team_id) === Number(team.id))))
        .map((team) => Number(team.id)));
    return new Set([...full, ...catalogState.entryTeamIds.map(Number)]);
}

function filteredPickerTeams() {
    const query = byId('entryTeamInput').value.trim().toLowerCase();
    const excluded = pickerExcludedIds();
    return catalogState.teams.filter((team) => {
        if (excluded.has(Number(team.id))) return false;
        return !query || (team.name || '').toLowerCase().includes(query);
    });
}

function renderTeamChips() {
    const box = byId('entryTeamBox');
    box.querySelectorAll('.team-chip').forEach((chip) => chip.remove());
    const input = byId('entryTeamInput');
    catalogState.entryTeamIds.forEach((id) => {
        const team = catalogState.teams.find((item) => Number(item.id) === Number(id));
        if (!team) return;
        const chip = document.createElement('span');
        chip.className = 'team-chip';
        chip.innerHTML = `${escapeHtml(team.name)}
            <button type="button" data-drop-team="${team.id}"
                aria-label="Убрать ${escapeHtml(team.name)}">&times;</button>`;
        box.insertBefore(chip, input);
    });
    input.placeholder = catalogState.entryTeamIds.length
        ? 'Добавить ещё' : 'Начните вводить название';
}

function renderTeamPickerList() {
    const list = byId('entryTeamList');
    const teams = filteredPickerTeams();
    if (!teams.length) {
        list.innerHTML = `<p class="team-picker-empty">${byId('entryTeamInput').value.trim()
            ? 'Команда не найдена'
            : 'Все команды уже заявлены в этой категории'}</p>`;
        return;
    }
    list.innerHTML = teams.map((team, index) => `
        <button class="team-picker-option${index === catalogState.entryTeamHighlight ? ' active' : ''}"
            type="button" role="option" aria-selected="false" data-pick-team="${team.id}">
            <span class="catalog-row-icon">
                ${team.logo_url
                    ? `<img src="${escapeHtml(team.logo_url)}" alt="">`
                    : `<span>${escapeHtml(initials(team.name))}</span>`}
            </span>
            <span class="team-picker-name">${escapeHtml(team.name)}</span>
            <small>${escapeHtml(pluralizeMembers(Number(team.member_count) || 0))}</small>
        </button>`).join('');
}

function openTeamPicker() {
    catalogState.entryTeamHighlight = -1;
    renderTeamPickerList();
    byId('entryTeamList').hidden = false;
    byId('entryTeamInput').setAttribute('aria-expanded', 'true');
}

function closeTeamPicker() {
    byId('entryTeamList').hidden = true;
    byId('entryTeamInput').setAttribute('aria-expanded', 'false');
}

function pickTeam(teamId) {
    const team = catalogState.teams.find((item) => Number(item.id) === Number(teamId));
    if (!team || catalogState.entryTeamIds.includes(team.id)) return;
    catalogState.entryTeamIds.push(team.id);
    // Список не закрываем: сразу можно выбрать следующую команду.
    byId('entryTeamInput').value = '';
    catalogState.entryTeamHighlight = -1;
    renderTeamChips();
    renderTeamPickerList();
    byId('entryTeamInput').focus();
}

function dropTeamChip(teamId) {
    catalogState.entryTeamIds = catalogState.entryTeamIds
        .filter((id) => Number(id) !== Number(teamId));
    renderTeamChips();
    renderTeamPickerList();
}

function moveTeamHighlight(step) {
    const teams = filteredPickerTeams();
    if (!teams.length) return;
    const next = catalogState.entryTeamHighlight + step;
    catalogState.entryTeamHighlight = (next + teams.length) % teams.length;
    renderTeamPickerList();
    byId('entryTeamList').querySelector('.team-picker-option.active')
        ?.scrollIntoView({ block: 'nearest' });
}

function renderEntryPickers() {
    renderTeamChips();
    if (!byId('entryTeamList').hidden) renderTeamPickerList();

    const groups = catalogState.entryAgeGroups;
    // По умолчанию отмечена категория, которая сейчас открыта; можно добавить и другие.
    let picked = (catalogState.entryAges || []).filter((age) => groups.includes(age));
    if (!picked.length) picked = groups.includes(catalogState.age) ? [catalogState.age] : groups.slice(0, 1);
    catalogState.entryAges = picked;
    byId('entryAgeField').hidden = groups.length < 2;
    byId('entryAgeChips').innerHTML = groups.map((age) => `
        <label class="age-pick${picked.includes(age) ? ' on' : ''}">
            <input type="checkbox" value="${escapeHtml(age)}" ${picked.includes(age) ? 'checked' : ''}>
            <span>${escapeHtml(age)}</span>
        </label>`).join('');
}

function otherCategories(entry) {
    return catalogState.entries
        .filter((item) => Number(item.team_id) === Number(entry.team_id) && item.age_group !== entry.age_group
            && item.status !== 'declined')
        .map((item) => item.age_group)
        .join(', ');
}

function renderEntries() {
    const list = byId('entriesList');
    const entries = catalogState.entries.filter((entry) =>
        !catalogState.age || entry.age_group === catalogState.age);
    renderEntryRing();

    if (!entries.length) {
        list.innerHTML = emptyCatalogMarkup(
            'users-round',
            'Участников пока нет',
            `Добавьте команды категории ${catalogState.age || ''}, которые будут играть на турнире.`,
        );
        refreshIcons();
        return;
    }

    // Группируем по категории: на турнире с двумя возрастами это две таблицы.
    const byAge = new Map();
    // Сначала подтвердившие: именно они играют.
    [...entries].sort((a, b) => ENTRY_STATUS_ORDER.indexOf(a.status) - ENTRY_STATUS_ORDER.indexOf(b.status))
        .forEach((entry) => {
            if (!byAge.has(entry.age_group)) byAge.set(entry.age_group, []);
            byAge.get(entry.age_group).push(entry);
        });

    list.innerHTML = [...byAge.entries()].map(([, items]) => `
        <section class="entry-group">
            <div class="catalog-table-wrap">
                <table class="catalog-data-table">
                    <thead>
                        <tr>
                            <th>Команда</th>
                            <th>Игроки</th>
                            <th>Статус</th>
                            <th aria-label="Действия"></th>
                        </tr>
                    </thead>
                    <tbody>
                        ${items.map((entry) => `
                            <tr>
                                <td data-label="Команда" title="${escapeHtml([entry.trainer_name, entry.trainer_phone].filter(Boolean).join(' · ') || 'Тренер не указан')}">
                                    <span class="catalog-primary-cell">
                                        <span class="catalog-row-icon">
                                            ${entry.team_logo_url
                                                ? `<img src="${escapeHtml(entry.team_logo_url)}" alt="">`
                                                : `<span>${escapeHtml(initials(entry.team_name))}</span>`}
                                        </span>
                                        <span class="entry-team-name">
                                            <strong>${escapeHtml(entry.team_name)}</strong>
                                            ${otherCategories(entry) ? `<small>ещё: ${escapeHtml(otherCategories(entry))}</small>` : ''}
                                        </span>
                                    </span>
                                </td>
                                <td data-label="Состав">${rosterCellMarkup(entry)}</td>
                                <td data-label="Статус">
                                    <select class="entry-status entry-status-${escapeHtml(entry.status)}"
                                        data-entry-status="${entry.id}">
                                        ${ENTRY_STATUS_ORDER.map((code) => `
                                            <option value="${code}" ${entry.status === code ? 'selected' : ''}>
                                                ${code === 'confirmed' ? 'Подтвердила'
                                                    : code === 'invited' ? 'Приглашена' : 'Отказалась'}
                                            </option>`).join('')}
                                    </select>
                                </td>
                                <td class="team-member-actions">
                                    <button class="icon-button danger" type="button"
                                        data-delete-entry="${entry.id}" aria-label="Убрать из турнира">
                                        <i data-lucide="trash-2"></i>
                                    </button>
                                </td>
                            </tr>`).join('')}
                    </tbody>
                </table>
            </div>
        </section>`).join('');
    refreshIcons();
}

async function loadEntries() {
    const data = await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}/entries`);
    catalogState.entries = data.entries || [];
    catalogState.entryAgeGroups = data.age_groups || [];
    if (!catalogState.entryAgeGroups.includes(catalogState.age)) {
        setCategory(catalogState.entryAgeGroups[0] || '');
    }
    renderCategorySwitch();
    renderEntryPickers();
    renderEntries();
}

async function switchCategory(age) {
    if (age === catalogState.age) return;
    setCategory(age);
    catalogState.entryAges = [];
    catalogState.formatDirty = false;
    catalogState.playersStats = null;
    catalogState.playersAwards = [];
    renderCategorySwitch();
    renderEntryPickers();
    renderEntries();
    await loadCategory();
    if (catalogState.entryTab === 'players') await loadPlayers();
}

function switchEntryTab(name) {
    catalogState.entryTab = name;
    document.querySelectorAll('[data-entry-tab]').forEach((button) => {
        button.classList.toggle('active', button.dataset.entryTab === name);
    });
    document.querySelectorAll('[data-entry-panel]').forEach((panel) => {
        panel.hidden = panel.dataset.entryPanel !== name;
    });
}

async function openTournamentEntries(tournamentId) {
    const tournament = catalogState.tournaments.find((row) => Number(row.id) === Number(tournamentId));
    if (!tournament) return;
    catalogState.entriesTournamentId = tournament.id;
    catalogState.entries = [];
    byId('entriesTournamentTitle').textContent = tournament.name;
    renderEntryTournamentCard(tournament);
    showFormError('entryFormError');
    openModal('tournamentEntriesModal');
    switchEntryTab('entries');
    catalogState.playersStats = null;
    catalogState.playersAwards = [];
    catalogState.overview = null;
    catalogState.formatDirty = false;
    setCategory('');
    await loadEntries();
    renderScreenLink();
    await loadCategory();
    // Открываем тот шаг, на котором организатор остановился.
    const steps = catalogState.overview?.steps || {};
    if (steps.entries && !steps.finished) switchEntryTab('board');
    renderSteps();
}

async function addTournamentEntry() {
    const ageGroups = selectedEntryAges();
    const teamIds = [...catalogState.entryTeamIds];
    if (!teamIds.length) {
        showFormError('entryFormError', 'Выберите команды из списка');
        return;
    }
    if (!ageGroups.length) {
        showFormError('entryFormError', 'Отметьте хотя бы одну возрастную категорию');
        return;
    }
    try {
        showFormError('entryFormError');
        const result = await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}/entries`, {
            method: 'POST',
            body: JSON.stringify({ team_ids: teamIds, age_groups: ageGroups }),
        });
        byId('entryTeamInput').value = '';
        catalogState.entryTeamIds = [];
        renderTeamChips();
        const notice = byId('entryNotice');
        notice.hidden = !(result.added || []).length;
        notice.textContent = `Заявлено: ${(result.added || []).join(', ')}`;
        window.clearTimeout(catalogState.entryNoticeTimer);
        catalogState.entryNoticeTimer = window.setTimeout(() => { notice.hidden = true; }, 5000);
        if (result.skipped && result.skipped.length) {
            showFormError('entryFormError',
                `Уже были заявлены: ${result.skipped.join(', ')}`);
        }
        await loadEntries();
        await loadCategory();
    } catch (error) {
        showFormError('entryFormError', error.message);
    }
}

async function updateEntryStatus(entryId, status) {
    const data = categoryOverview();
    if (data?.built && !data.has_results && !window.confirm(
        'Календарь категории уже составлен. После смены статуса его нужно будет собрать заново. Продолжить?')) {
        renderEntries();
        return;
    }
    try {
        showFormError('entryFormError');
        const result = await apiJson(`/api/tournament-entries/${entryId}`, {
            method: 'PUT',
            body: JSON.stringify({ status }),
        });
        await loadEntries();
        await loadCategory();
        if (result.calendar_reset) {
            showFormError('entryFormError', 'Состав изменился — календарь сброшен. '
                + 'Соберите его заново на шаге «Схема».');
        }
    } catch (error) {
        showFormError('entryFormError', error.message);
        await loadEntries();
    }
}

async function deleteTournamentEntry(entryId) {
    const entry = catalogState.entries.find((item) => Number(item.id) === Number(entryId));
    if (!entry || !window.confirm(`Убрать «${entry.team_name}» из турнира?`)) return;
    try {
        showFormError('entryFormError');
        await apiJson(`/api/tournament-entries/${entryId}`, { method: 'DELETE' });
        await loadEntries();
        await loadCategory();
    } catch (error) {
        showFormError('entryFormError', error.message);
    }
}

/* --- Категория турнира: одна точка правды для всех этапов --- */

const FORMAT_TITLES = {
    groups_playoff: 'Группы + плей-офф',
    league: 'Круговой турнир',
    knockout: 'Олимпийская система',
};

function categoryOverview() {
    return catalogState.overview;
}

function currentFormat() {
    return catalogState.overview?.settings?.format || 'groups_playoff';
}

function setCategory(age) {
    catalogState.age = age || '';
    catalogState.groupAge = catalogState.age;
    catalogState.matchAge = catalogState.age;
    catalogState.playoffAge = catalogState.age;
    catalogState.playersAge = catalogState.age;
}

function renderCategorySwitch() {
    const box = byId('categorySwitch');
    const ages = catalogState.entryAgeGroups;
    box.innerHTML = ages.map((age) => {
        const count = catalogState.entries.filter((entry) =>
            entry.age_group === age && entry.status === 'confirmed').length;
        return `<button type="button" role="tab" data-category="${escapeHtml(age)}"
            aria-selected="${age === catalogState.age}" class="${age === catalogState.age ? 'active' : ''}">
            ${escapeHtml(age)}<small>${count}</small></button>`;
    }).join('');
    box.closest('.category-switch-row').hidden = ages.length < 2;
}

async function loadCategory() {
    if (!catalogState.age) {
        catalogState.overview = null;
        renderCategory();
        return;
    }
    const data = await apiJson(
        `/api/tournaments/${catalogState.entriesTournamentId}/category`
        + `?age_group=${encodeURIComponent(catalogState.age)}`,
    );
    catalogState.overview = data;
    catalogState.groups = data.groups || [];
    catalogState.groupEntries = data.entries || [];
    catalogState.matchBlocks = data.blocks || [];
    catalogState.matchStadiums = data.stadiums || [];
    catalogState.playoffMatches = data.playoff || [];
    catalogState.playoffResults = data.results || [];
    renderCategory();
}

const MEDALS = { 1: 'gold', 2: 'silver', 3: 'bronze' };

/* Итоговая таблица мест — во вкладке «Награды», с эмблемами команд. */
function renderFinalStandings() {
    const host = byId('finalStandings');
    const data = categoryOverview();
    const results = data?.results || [];
    if (!host) return;
    if (!results.length) {
        host.innerHTML = '';
        return;
    }
    const total = data?.counts?.confirmed || results.length;
    host.innerHTML = `
        <section class="final-table">
            <header>
                <h3>Итоговые места</h3>
                <span>${results.length < total ? `определено ${results.length} из ${total}` : 'турнир завершён'}</span>
            </header>
            <ol>
                ${results.map((row) => `
                    <li class="final-row ${MEDALS[row.place] || ''}">
                        <span class="final-place">${row.place}</span>
                        <span class="final-logo">${row.team_logo_url
                            ? `<img src="${escapeHtml(row.team_logo_url)}" alt="">`
                            : escapeHtml(initials(row.team_name))}</span>
                        <strong>${escapeHtml(row.team_name)}</strong>
                        ${MEDALS[row.place] ? `<span class="final-medal" aria-hidden="true">${
                            { 1: '🥇', 2: '🥈', 3: '🥉' }[row.place]}</span>` : ''}
                    </li>`).join('')}
            </ol>
        </section>`;
}

function renderCategory() {
    renderTiebreak();
    renderSteps();
    renderFinalStandings();
    // Полотно турнира (tournament_board.js) встраивается сюда же.
}

/* Шаги: что уже сделано и куда идти дальше */

function renderSteps() {
    const data = categoryOverview();
    const steps = data?.steps || {};
    // Три шага: заявки → турнир (группы, матчи, сетка на одном полотне) → награды.
    const marks = {
        entries: steps.entries,
        board: data?.built && steps.groups && steps.playoff,
        players: steps.finished,
    };
    document.querySelectorAll('[data-entry-tab]').forEach((button) => {
        button.classList.toggle('done', Boolean(marks[button.dataset.entryTab]));
    });
    // Следующий шаг — оранжевая точка на вкладке.
    let next = '';
    if (data) {
        if (!steps.entries) next = 'entries';
        else if (!marks.board) next = 'board';
        else next = 'players';
    }
    document.querySelectorAll('[data-entry-tab]').forEach((button) => {
        button.classList.toggle('next', button.dataset.entryTab === next && !button.classList.contains('done'));
    });
}

function splitSizes(total, groups) {
    const base = Math.floor(total / groups);
    const extra = total % groups;
    return Array.from({ length: groups }, (_, index) => base + (index < extra ? 1 : 0));
}

function roundName(matches) {
    return { 1: 'Финал', 2: 'Полуфинал', 4: '1/4 финала', 8: '1/8 финала', 16: '1/16 финала' }[matches]
        || `1/${matches} финала`;
}

function pluralizeMatches(count) {
    const tail = count % 10;
    const tens = count % 100;
    if (tail === 1 && tens !== 11) return `${count} матч`;
    if (tail >= 2 && tail <= 4 && (tens < 12 || tens > 14)) return `${count} матча`;
    return `${count} матчей`;
}

const TIEBREAK_OPTIONS = [
    { key: 'h2h', title: 'По личным встречам', hint: 'Выше тот, кто выиграл матч между ними' },
    { key: 'overall', title: 'По разнице мячей', hint: 'Выше тот, у кого лучше разница во всех матчах группы' },
];

function tiebreakTitle(key) {
    return key === 'overall' ? 'разница мячей' : 'личные встречи';
}

function tiebreakNoteMarkup() {
    const rule = categoryOverview()?.rules?.tiebreak;
    return rule ? `<p class="tiebreak-note">При равенстве очков: ${escapeHtml(tiebreakTitle(rule))}</p>` : '';
}

function renderTiebreak() {
    const data = categoryOverview();
    const current = data?.rules?.tiebreak || 'h2h';
    const locked = Boolean(data?.rules_locked);
    const help = TIEBREAK_OPTIONS.map((option) => `${option.title}: ${option.hint.toLowerCase()}.`).join('\n')
        + '\nПравило одно для всех групп и категорий турнира.';
    document.querySelectorAll('[data-tiebreak-host]').forEach((host) => {
        host.innerHTML = `
            <label class="tiebreak-inline" title="${escapeHtml(help)}">
                <span>При равенстве очков</span>
                <select data-tiebreak-select ${locked ? 'disabled' : ''} aria-label="Правило при равенстве очков">
                    ${TIEBREAK_OPTIONS.map((option) => `<option value="${option.key}" ${option.key === current
                        ? 'selected' : ''}>${escapeHtml(option.title.toLowerCase())}</option>`).join('')}
                </select>
                <i class="tiebreak-help" aria-hidden="true">?</i>
                ${locked ? '<small>закреплено — матчи идут</small>' : ''}
            </label>`;
    });
    // В олимпийской системе таблиц нет — правило не нужно.
    const knockout = data?.settings?.format === 'knockout';
    byId('boardTiebreak').hidden = knockout || !data?.groups?.length;
}

async function setTiebreak(key) {
    const data = categoryOverview();
    if (!data || data.rules?.tiebreak === key) return;
    try {
        await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}/rules`, {
            method: 'PUT',
            body: JSON.stringify({ tiebreak: key }),
        });
        await loadCategory();
    } catch (error) {
        showPageError(error);
    }
}

async function resetCategory() {
    if (!window.confirm(`Удалить календарь, сетку, счета и протоколы категории ${catalogState.age}? `
        + 'Заявки и группы останутся.')) return;
    if (categoryOverview()?.has_results
        && window.prompt('Есть сыгранные матчи. Для подтверждения введите слово СБРОС') !== 'СБРОС') return;
    try {
        await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}/reset`, {
            method: 'POST',
            body: JSON.stringify({ age_group: catalogState.age }),
        });
        catalogState.formatDirty = false;
        await loadCategory();
    } catch (error) {
        showFormError('boardError', error.message);
    }
}

/* Перетаскивание карточек между колонками: мышью сразу, пальцем — после удержания.
 * canDrop(item, zone) подсвечивает, куда нельзя; onDrop(item, zone) сохраняет. */
function bindDragBoard(board, { item, zone, canDrop = () => true, onDrop, isLocked = () => false }) {
    let drag = null;

    const clearHighlight = () => board.querySelectorAll(`${zone}.over, ${zone}.blocked`)
        .forEach((el) => el.classList.remove('over', 'blocked'));

    function startDrag(event) {
        drag.active = true;
        drag.el.classList.add('dragging');
        const rect = drag.el.getBoundingClientRect();
        drag.ghost = drag.el.cloneNode(true);
        drag.ghost.classList.add('drag-ghost');
        drag.ghost.style.width = `${rect.width}px`;
        document.body.appendChild(drag.ghost);
        drag.offsetX = event.clientX - rect.left;
        drag.offsetY = event.clientY - rect.top;
        moveGhost(event);
    }

    function moveGhost(event) {
        drag.ghost.style.left = `${event.clientX - drag.offsetX}px`;
        drag.ghost.style.top = `${event.clientY - drag.offsetY}px`;
    }

    function zoneAt(event) {
        drag.ghost.style.display = 'none';
        const element = document.elementFromPoint(event.clientX, event.clientY);
        drag.ghost.style.display = '';
        return element ? element.closest(zone) : null;
    }

    function cleanup() {
        if (!drag) return;
        window.clearTimeout(drag.timer);
        drag.el.classList.remove('dragging');
        drag.ghost?.remove();
        clearHighlight();
        drag = null;
    }

    board.addEventListener('pointerdown', (event) => {
        const el = event.target.closest(item);
        // Выпадающий список внутри карточки не должен запускать перенос.
        if (!el || isLocked() || event.target.closest('select, button, input')
            || (event.pointerType === 'mouse' && event.button !== 0)) return;
        drag = {
            el,
            from: el.closest(zone),
            startX: event.clientX,
            startY: event.clientY,
            touch: event.pointerType !== 'mouse',
            active: false,
            timer: null,
        };
        // На пальце ждём удержания, иначе жест прокрутки превратится в перенос.
        if (drag.touch) {
            const pointer = { clientX: event.clientX, clientY: event.clientY };
            drag.timer = window.setTimeout(() => { if (drag) startDrag(pointer); }, 260);
        }
    });

    board.addEventListener('pointermove', (event) => {
        if (!drag) return;
        const shift = Math.hypot(event.clientX - drag.startX, event.clientY - drag.startY);
        if (!drag.active) {
            if (drag.touch) {
                if (shift > 12) cleanup();
                return;
            }
            if (shift < 5) return;
            startDrag(event);
        }
        event.preventDefault();
        moveGhost(event);
        clearHighlight();
        const target = zoneAt(event);
        if (target) target.classList.add(canDrop(drag.el, target) ? 'over' : 'blocked');
    });

    const finish = (event) => {
        if (!drag) return;
        if (drag.active) {
            const target = zoneAt(event);
            const { el, from } = drag;
            const allowed = target && target !== from && canDrop(el, target);
            cleanup();
            if (allowed) Promise.resolve(onDrop(el, target)).catch(showPageError);
            return;
        }
        cleanup();
    };

    board.addEventListener('pointerup', finish);
    board.addEventListener('pointercancel', () => cleanup());
}

function openScheduleDialog() {
    const tournament = catalogState.tournaments
        .find((row) => Number(row.id) === Number(catalogState.entriesTournamentId));
    if (tournament) {
        byId('scheduleStartDate').value = tournament.start_date || '';
        byId('scheduleStartTime').value = tournament.start_time || '10:00';
    }
    const select = byId('scheduleStadium');
    select.innerHTML = ['<option value="">Не менять</option>']
        .concat(catalogState.matchStadiums.map((item) =>
            `<option value="${item.id}">${escapeHtml(item.name)}</option>`))
        .join('');
    showFormError('scheduleError');
    byId('scheduleResult').hidden = true;
    openModal('scheduleModal');
}

async function runSchedule() {
    const button = byId('runScheduleBtn');
    button.disabled = true;
    try {
        showFormError('scheduleError');
        const data = await apiJson(
            `/api/tournaments/${catalogState.entriesTournamentId}/matches/schedule`,
            {
                method: 'POST',
                body: JSON.stringify({
                    start_date: byId('scheduleStartDate').value,
                    start_time: byId('scheduleStartTime').value,
                    end_time: byId('scheduleEndTime').value,
                    duration: Number(byId('scheduleDuration').value),
                    gap: Number(byId('scheduleGap').value),
                    pitches: Number(byId('schedulePitches').value),
                    stadium_id: byId('scheduleStadium').value || null,
                    only_current: byId('scheduleOnlyCurrent').checked,
                    overwrite: byId('scheduleOverwrite').checked,
                    age_group: catalogState.age,
                }),
            },
        );
        byId('scheduleResult').hidden = false;
        byId('scheduleStatus').textContent = data.days > 1
            ? `Расставлено: ${pluralizeMatches(data.scheduled)} на ${data.days} дн.: ${formatDate(data.first)} — ${formatDate(data.last)}`
            : `Расставлено: ${pluralizeMatches(data.scheduled)} на ${formatDate(data.first)}`;
        await loadCategory();
    } catch (error) {
        showFormError('scheduleError', error.message);
    } finally {
        button.disabled = false;
    }
}

function formatKickoff(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return value;
    return date.toLocaleString('ru-RU', { day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
}

/* --- Состав по категориям: кто из игроков клуба где играет --- */

function rosterCellMarkup(entry) {
    const waiting = Number(entry.team_unassigned) || 0;
    const count = entry.roster_used ? entry.roster_count : entry.member_count;
    return `
        <button type="button" class="roster-chip${waiting ? ' warn' : ''}" data-roster-team="${entry.team_id}"
            title="Кто из игроков клуба играет в этой категории">
            <span>${count}</span>
            ${waiting ? `<em title="${waiting} игрок(а) ждут, в какую категорию их поставить">+${waiting} ?</em>` : ''}
            <i data-lucide="chevron-right"></i>
        </button>`;
}

async function openRoster(teamId) {
    catalogState.rosterTeamId = Number(teamId);
    showFormError('rosterError');
    await loadRoster();
    openModal('rosterModal');
}

async function loadRoster() {
    const data = await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}`
        + `/teams/${catalogState.rosterTeamId}/roster`);
    catalogState.roster = data;
    renderRoster();
}

function rosterPlayerMarkup(player, categories) {
    const meta = [
        player.birth_year ? `${player.birth_year} г.р.` : null,
        player.number ? `№${player.number}` : null,
        player.position ? POSITION_SHORT[player.position] || player.position : null,
    ].filter(Boolean).join(' · ');
    // Список — это действие: «выбрать категорию» или «перенести», а не повтор названия колонки.
    const targets = categories.filter((category) => category.entry_id !== player.entry_id
        && player.eligible.includes(category.entry_id));
    const options = [`<option value="__keep" selected>${player.entry_id ? 'Перенести…' : 'Выбрать категорию…'}</option>`]
        .concat(targets.map((category) =>
            `<option value="${category.entry_id}">${escapeHtml(category.age_group)}</option>`))
        .concat(player.entry_id ? ['<option value="">Убрать из категории</option>'] : []);
    const flag = player.violates
        ? '<span class="roster-flag bad">не по возрасту</span>'
        : player.is_auto ? '<span class="roster-flag auto" title="Поставлен автоматически по году рождения">авто</span>' : '';
    return `
        <div class="roster-player${player.violates ? ' violates' : ''}${player.issue ? ' muted' : ''}"
            data-member="${player.id}" data-eligible="${player.eligible.join(',')}">
            <span class="roster-face"${player.photo_url ? ` style="background-image:url('${escapeHtml(player.photo_url)}')"` : ''}>
                ${player.photo_url ? '' : escapeHtml(initials(player.name))}</span>
            <span class="roster-info">
                <strong>${escapeHtml(player.name)}</strong>
                <small>${escapeHtml(meta || 'Данные не заполнены')}</small>
            </span>
            ${flag}
            ${!player.eligible.length && !player.entry_id
                ? `<span class="roster-fix">${player.issue === 'no_birth_date'
                    ? 'Укажите дату рождения в карточке команды'
                    : player.issue === 'too_young'
                        ? 'Включите «Младшие могут играть за старших», если регламент разрешает'
                        : 'По возрасту не подходит ни в одну категорию'}</span>`
                : `<select class="roster-move" data-move="${player.id}"
                    aria-label="Категория для ${escapeHtml(player.name)}">${options.join('')}</select>`}
        </div>`;
}

function renderRoster() {
    const data = catalogState.roster;
    if (!data) return;
    byId('rosterTitle').textContent = data.team.name;
    byId('rosterPlayUp').checked = Boolean(data.rules.allow_play_up);
    const categories = data.categories.filter((category) => !category.declined);
    const declined = data.categories.filter((category) => category.declined);
    const free = data.players.filter((player) => !player.entry_id);
    const waiting = free.filter((player) => player.eligible.length);
    const blocked = free.filter((player) => !player.eligible.length);

    const summary = byId('rosterSummary');
    if (!data.players.length) {
        summary.className = 'roster-summary warn';
        summary.textContent = 'В клубе пока нет игроков.';
    } else if (waiting.length) {
        summary.className = 'roster-summary warn';
        summary.textContent = `Выберите категорию для ${waiting.length} — перетащите карточку или выберите в списке.`;
    } else {
        summary.className = 'roster-summary';
        summary.textContent = '';
    }
    summary.hidden = !summary.textContent;

    const column = (title, sub, zone, players, extra = '') => `
        <section class="roster-column${zone === '' ? ' free' : ''}">
            <header>
                <strong>${escapeHtml(title)}</strong>
                <span>${escapeHtml(sub)}</span>
            </header>
            <div class="roster-drop" data-roster-drop="${zone}">
                ${players.map((player) => rosterPlayerMarkup(player, categories)).join('')
                    || `<p class="group-empty">${zone === '' ? 'Все распределены' : 'Перетащите игроков сюда'}</p>`}
            </div>
            ${extra}
        </section>`;

    const blockedMarkup = blocked.length ? `
        <div class="roster-blocked">
            <p>Не могут играть ни в одной категории клуба:</p>
            ${blocked.map((player) => rosterPlayerMarkup(player, categories)).join('')}
        </div>` : '';

    byId('rosterBoard').innerHTML = [
        column('Не распределены', pluralizeMembers(waiting.length), '', waiting, blockedMarkup),
        ...categories.map((category) => {
            const players = data.players.filter((player) => player.entry_id === category.entry_id);
            return column(category.age_group, `${category.years} · ${pluralizeMembers(players.length)}`,
                String(category.entry_id), players);
        }),
    ].join('');
    byId('rosterDeclined').hidden = !declined.length;
    byId('rosterDeclined').textContent = declined.length
        ? `Отказались: ${declined.map((category) => category.age_group).join(', ')} — эти категории здесь не показаны.`
        : '';
    refreshIcons();
}

async function moveRosterPlayer(memberId, entryId) {
    try {
        showFormError('rosterError');
        const data = await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}/roster`, {
            method: 'PUT',
            body: JSON.stringify({ member_id: Number(memberId), entry_id: entryId ? Number(entryId) : null }),
        });
        catalogState.roster = data;
        renderRoster();
        catalogState.rosterDirty = true;
    } catch (error) {
        showFormError('rosterError', error.message);
        renderRoster();
    }
}

async function setPlayUp(enabled) {
    try {
        showFormError('rosterError');
        await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}/rules`, {
            method: 'PUT',
            body: JSON.stringify({ allow_play_up: enabled }),
        });
        await loadRoster();
        catalogState.rosterDirty = true;
    } catch (error) {
        showFormError('rosterError', error.message);
    }
}

function bindRosterModal() {
    const board = byId('rosterBoard');
    bindDragBoard(board, {
        item: '[data-member]',
        zone: '[data-roster-drop]',
        canDrop: (el, target) => !target.dataset.rosterDrop
            || el.dataset.eligible.split(',').includes(target.dataset.rosterDrop),
        onDrop: (el, target) => moveRosterPlayer(el.dataset.member, target.dataset.rosterDrop),
    });
    board.addEventListener('change', (event) => {
        const select = event.target.closest('[data-move]');
        if (select && select.value !== '__keep') moveRosterPlayer(select.dataset.move, select.value);
    });
    byId('rosterPlayUp').addEventListener('change', (event) => setPlayUp(event.target.checked));
    byId('rosterOpenTeam').addEventListener('click', () => {
        closeRosterModal();
        openTeamDetails(catalogState.rosterTeamId).catch(showPageError);
    });
    // После правок обновляем счётчики в списке участников.
    byId('rosterModal').addEventListener('roster:closed', () => {
        if (!catalogState.rosterDirty) return;
        catalogState.rosterDirty = false;
        loadEntries().catch(showPageError);
    });
}

function closeRosterModal() {
    closeModal('rosterModal');
}

/* --- Студия публикаций: картинку рисует сервер, превью = готовый файл --- */

const STUDIO_BACKGROUNDS = [
    { key: 'none', title: 'Заливка темы' },
    { key: 'poster', title: 'Афиша турнира' },
    { key: 'custom', title: 'Своя картинка' },
];

const studio = {
    options: null,
    template: 'announce',
    background: 'none',
    accent: '#ff9a2b',
    backgroundPath: null,
    blobUrl: null,
    timer: null,
    busy: false,
    again: false,
};

function studioValue(id) {
    const element = byId(id);
    return element ? element.value : '';
}

function studioChips(host, items, current, attribute) {
    byId(host).innerHTML = items.map((item) => `
        <button type="button" class="studio-chip${item.key === current ? ' active' : ''}"
            data-${attribute}="${escapeHtml(item.key)}">${escapeHtml(item.title)}</button>`).join('');
}

function studioSelect(id, items, valueKey, titleKey) {
    byId(id).innerHTML = items.map((item) =>
        `<option value="${escapeHtml(String(item[valueKey]))}">${escapeHtml(item[titleKey])}</option>`).join('');
}

function studioSourceItems() {
    const options = studio.options;
    const age = studioValue('studioAge');
    if (studio.template === 'match') {
        return (options.matches || []).filter((row) => !age || row.age_group === age)
            .map((row) => ({ value: String(row.id), title: row.label }));
    }
    if (studio.template === 'standings') {
        return (options.groups || []).filter((row) => !age || row.age_group === age)
            .map((row) => ({ value: String(row.id), title: `Группа ${row.name}` }));
    }
    if (studio.template === 'award') {
        return (options.awards || []).filter((row) => !age || row.age_group === age)
            .map((row) => ({ value: row.code, title: row.title }));
    }
    return [];
}

function renderStudioSource() {
    const items = studioSourceItems();
    const field = byId('studioSourceField');
    const labels = { match: 'Матч', standings: 'Группа', award: 'Награда' };
    field.hidden = !labels[studio.template];
    if (field.hidden) return;
    byId('studioSourceLabel').textContent = labels[studio.template];
    byId('studioSource').innerHTML = items.length
        ? items.map((item) =>
            `<option value="${escapeHtml(item.value)}">${escapeHtml(item.title)}</option>`).join('')
        : '<option value="">нет данных</option>';
}

function studioPayload() {
    const source = studioValue('studioSource');
    const payload = {
        template: studio.template,
        format: studioValue('studioFormat'),
        theme: studioValue('studioTheme'),
        font: studioValue('studioFont'),
        accent: studio.accent,
        background: studio.background === 'none' ? null : studio.background,
        background_path: studio.backgroundPath,
        shade: Number(studioValue('studioShade') || 70),
        blur: byId('studioBlur').checked,
        age_group: studioValue('studioAge'),
        eyebrow: studioValue('studioEyebrow'),
        caption: studioValue('studioCaption'),
        title: studioValue('studioTitle'),
        subtitle: studioValue('studioSubtitle'),
        note: studioValue('studioNote'),
    };
    if (studio.template === 'match') payload.match_id = source;
    if (studio.template === 'standings') payload.group_id = source;
    if (studio.template === 'award') payload.award_code = source;
    return payload;
}

async function renderStudio() {
    // Пока рисуется предыдущий кадр, новый ставим в очередь: иначе быстрый
    // ввод текста завалит сервер десятком одинаковых запросов.
    if (studio.busy) { studio.again = true; return; }
    studio.busy = true;
    byId('studioSpinner').hidden = false;
    try {
        showFormError('studioError');
        const response = await fetch(
            `/api/tournaments/${catalogState.entriesTournamentId}/post.png`,
            {
                method: 'POST',
                credentials: 'same-origin',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(studioPayload()),
            });
        if (!response.ok) {
            const data = await response.json().catch(() => ({}));
            throw new Error(data.message || 'Не удалось собрать публикацию');
        }
        const blob = await response.blob();
        if (studio.blobUrl) URL.revokeObjectURL(studio.blobUrl);
        studio.blobUrl = URL.createObjectURL(blob);
        byId('studioImage').src = studio.blobUrl;
    } catch (error) {
        showFormError('studioError', error.message);
    } finally {
        studio.busy = false;
        byId('studioSpinner').hidden = true;
        if (studio.again) { studio.again = false; renderStudio(); }
    }
}

function scheduleStudio() {
    window.clearTimeout(studio.timer);
    studio.timer = window.setTimeout(() => renderStudio(), 350);
}

async function openStudio(preset = {}) {
    try {
        showFormError('studioError');
        const data = await apiJson(
            `/api/tournaments/${catalogState.entriesTournamentId}/post-options`);
        studio.options = data;
        studio.template = preset.template || 'announce';
        studio.background = data.has_poster ? 'poster' : 'none';
        studio.backgroundPath = null;

        studioChips('studioTemplates', data.templates.map(
            (row) => ({ key: row.key, title: row.title })), studio.template, 'template');
        studioChips('studioBackgrounds', STUDIO_BACKGROUNDS.filter(
            (row) => row.key !== 'poster' || data.has_poster), studio.background, 'background');
        studioSelect('studioFormat', data.formats, 'key', 'title');
        studioSelect('studioTheme', data.themes, 'key', 'title');
        studioSelect('studioFont', data.fonts, 'key', 'title');
        byId('studioAge').innerHTML = (data.age_groups || []).map((age) =>
            `<option value="${escapeHtml(age)}">${escapeHtml(age)}</option>`).join('');
        if (preset.age_group) byId('studioAge').value = preset.age_group;

        byId('studioAccents').innerHTML = (data.accents || []).map((color) => `
            <button type="button" class="studio-swatch${color === studio.accent ? ' active' : ''}"
                data-accent="${escapeHtml(color)}" style="background:${escapeHtml(color)} !important""
                aria-label="Цвет ${escapeHtml(color)}"></button>`).join('')
            + '<input type="color" id="studioAccentPicker" value="' + studio.accent + '">';

        ['studioEyebrow', 'studioCaption', 'studioTitle', 'studioSubtitle', 'studioNote']
            .forEach((id) => { byId(id).value = ''; });

        renderStudioSource();
        if (preset.match_id) byId('studioSource').value = String(preset.match_id);
        if (preset.award_code) byId('studioSource').value = preset.award_code;
        byId('studioShadeRow').hidden = studio.background === 'none';
        byId('studioUploadField').hidden = studio.background !== 'custom';

        openModal('postStudioModal');
        await renderStudio();
    } catch (error) {
        window.alert(error.message);
    }
}

async function uploadStudioBackground(file) {
    const form = new FormData();
    form.append('background', file);
    try {
        showFormError('studioError');
        const data = await apiJson('/api/tournament-post-background', { method: 'POST', body: form });
        studio.backgroundPath = data.background_path;
        renderStudio();
    } catch (error) {
        showFormError('studioError', error.message);
    }
}

function downloadStudio() {
    if (!studio.blobUrl) return;
    const link = document.createElement('a');
    link.href = studio.blobUrl;
    link.download = `${studio.template}-${studioValue('studioFormat')}.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
}

/* --- Протокол матча: составы, голы, карточки --- */

const POSITION_SHORT = {
    'Вратарь': 'вр.', 'Защитник': 'зщ.', 'Полузащитник': 'пз.', 'Нападающий': 'нап.',
};

function protocolSquadMarkup(side, block) {
    if (!block) return '';
    const lineup = new Map(block.lineup.map((row) => [row.member_id, row]));
    return `
        <section class="protocol-team" data-side="${side}">
            <header>
                <span class="protocol-logo"${block.team_logo_url
                    ? ` style="background-image:url('${escapeHtml(block.team_logo_url)}')"` : ''}></span>
                <strong>${escapeHtml(block.team_name)}</strong>
                <span class="protocol-count" data-count>${lineup.size}</span>
            </header>
            <div class="protocol-squad">
                ${block.squad.length ? block.squad.map((player) => {
                    const row = lineup.get(player.id);
                    return `
                    <label class="protocol-player${row ? ' on' : ''}" data-member="${player.id}">
                        <input type="checkbox" data-play ${row ? 'checked' : ''}>
                        <span class="protocol-face"${player.photo_url
                            ? ` style="background-image:url('${escapeHtml(player.photo_url)}')"` : ''}></span>
                        <span class="protocol-num">${escapeHtml(player.number || '')}</span>
                        <span class="protocol-name">${escapeHtml(player.name)}</span>
                        <span class="protocol-pos">${escapeHtml(
                            POSITION_SHORT[player.position] || player.position || '')}</span>
                        <button type="button" class="protocol-gk${row && row.is_goalkeeper ? ' on' : ''}"
                            data-gk title="Вратарь в этом матче">ВР</button>
                    </label>`;
                }).join('') : '<p class="match-empty">В команде нет игроков</p>'}
            </div>
        </section>`;
}

function protocolPlayers(side) {
    // В событиях выбираем только тех, кто отмечен вышедшим на поле.
    const block = catalogState.protocol[side];
    if (!block) return [];
    const on = new Set([...document.querySelectorAll(
        `.protocol-team[data-side="${side}"] .protocol-player input[data-play]:checked`)]
        .map((input) => Number(input.closest('.protocol-player').dataset.member)));
    return block.squad.filter((player) => on.has(player.id));
}

function eventRowMarkup(event, index) {
    const protocol = catalogState.protocol;
    const sideName = (side) => (protocol[side] ? protocol[side].team_name : side);
    // Автогол забивает игрок соперника, поэтому список берём с другой стороны.
    const authorSide = event.kind === 'goal' && event.is_own_goal
        ? (event.side === 'home' ? 'away' : 'home') : event.side;
    const options = (list, selected) => ['<option value="">— выберите игрока —</option>'].concat(
        list.map((player) => `<option value="${player.id}" ${
            Number(selected) === player.id ? 'selected' : ''}>${escapeHtml(player.name)}</option>`)).join('');

    return `
        <div class="protocol-event" data-index="${index}">
            <span class="protocol-kind ${event.kind}">${event.kind === 'goal' ? 'Гол' : 'Карточка'}</span>
            <select data-field="side" aria-label="Команда">
                <option value="home" ${event.side === 'home' ? 'selected' : ''}>${escapeHtml(sideName('home'))}</option>
                <option value="away" ${event.side === 'away' ? 'selected' : ''}>${escapeHtml(sideName('away'))}</option>
            </select>
            <select data-field="member_id" aria-label="Игрок">
                ${options(protocolPlayers(authorSide), event.member_id)}
            </select>
            ${event.kind === 'goal' ? `
                <select data-field="assist_member_id" aria-label="Ассистент">
                    <option value="">без ассиста</option>
                    ${protocolPlayers(event.side).map((player) =>
                        `<option value="${player.id}" ${Number(event.assist_member_id) === player.id
                            ? 'selected' : ''}>${escapeHtml(player.name)}</option>`).join('')}
                </select>
                <label class="protocol-flag"><input type="checkbox" data-field="is_own_goal"
                    ${event.is_own_goal ? 'checked' : ''}> автогол</label>
                <label class="protocol-flag"><input type="checkbox" data-field="is_penalty"
                    ${event.is_penalty ? 'checked' : ''}> с пенальти</label>`
            : `
                <select data-field="card" aria-label="Карточка">
                    <option value="yellow" ${event.card === 'yellow' ? 'selected' : ''}>жёлтая</option>
                    <option value="red" ${event.card === 'red' ? 'selected' : ''}>красная</option>
                </select>`}
            <input class="protocol-minute" type="number" min="0" max="200" data-field="minute"
                value="${event.minute === null || event.minute === undefined ? '' : event.minute}"
                placeholder="мин" aria-label="Минута">
            <button type="button" class="protocol-remove" data-remove-event title="Убрать">
                <i data-lucide="x"></i>
            </button>
        </div>`;
}

function renderProtocolEvents() {
    const box = byId('protocolEvents');
    const events = catalogState.protocolEvents;
    box.innerHTML = events.length
        ? events.map(eventRowMarkup).join('')
        : '<p class="match-empty">Событий пока нет</p>';

    const protocol = catalogState.protocol;
    const goals = { home: 0, away: 0 };
    events.forEach((event) => { if (event.kind === 'goal') goals[event.side] += 1; });
    const ok = goals.home === protocol.home_score && goals.away === protocol.away_score;
    const balance = byId('protocolBalance');
    balance.textContent = `Голов в протоколе ${goals.home}:${goals.away}`
        + ` · счёт ${protocol.home_score}:${protocol.away_score}`;
    balance.classList.toggle('ok', ok);
    balance.classList.toggle('bad', !ok);
    refreshIcons();
}

function renderProtocol() {
    const protocol = catalogState.protocol;
    byId('protocolTitle').textContent =
        `${protocol.home ? protocol.home.team_name : '—'} — ${protocol.away ? protocol.away.team_name : '—'}`;
    byId('protocolScore').textContent = `Счёт ${protocol.home_score}:${protocol.away_score}`;
    const poster = byId('protocolPoster');
    const tournament = catalogState.tournaments.find(
        (row) => Number(row.id) === Number(catalogState.entriesTournamentId));
    poster.style.backgroundImage = tournament && tournament.poster_url
        ? `url('${tournament.poster_url}')` : '';
    poster.classList.toggle('empty', !(tournament && tournament.poster_url));
    byId('protocolGrid').innerHTML =
        protocolSquadMarkup('home', protocol.home) + protocolSquadMarkup('away', protocol.away);
    renderProtocolEvents();
}

async function openProtocol(matchId) {
    try {
        showFormError('protocolError');
        const data = await apiJson(`/api/tournament-matches/${matchId}/protocol`);
        catalogState.protocol = data.protocol;
        catalogState.protocolEvents = (data.protocol.events || []).map((event) => ({
            side: event.entry_id === data.protocol.home.entry_id ? 'home' : 'away',
            kind: event.kind,
            member_id: event.member_id,
            assist_member_id: event.assist_member_id,
            minute: event.minute,
            is_own_goal: event.is_own_goal,
            is_penalty: event.is_penalty,
            card: event.card,
        }));
        openModal('matchProtocolModal');
        renderProtocol();
    } catch (error) {
        window.alert(error.message);
    }
}

function collectLineups() {
    const lineups = { home: [], away: [] };
    document.querySelectorAll('.protocol-team').forEach((team) => {
        const side = team.dataset.side;
        team.querySelectorAll('.protocol-player').forEach((row) => {
            if (!row.querySelector('[data-play]').checked) return;
            lineups[side].push({
                member_id: Number(row.dataset.member),
                is_starting: true,
                is_goalkeeper: row.querySelector('[data-gk]').classList.contains('on'),
            });
        });
    });
    return lineups;
}

async function saveProtocol() {
    try {
        showFormError('protocolError');
        const data = await apiJson(`/api/tournament-matches/${catalogState.protocol.match_id}/protocol`, {
            method: 'PUT',
            body: JSON.stringify({
                lineups: collectLineups(),
                events: catalogState.protocolEvents,
            }),
        });
        catalogState.protocol = data.protocol;
        closeModal('matchProtocolModal');
        if (catalogState.entryTab === 'players') await loadPlayers();
    } catch (error) {
        showFormError('protocolError', error.message);
    }
}

/* --- Игроки и награды --- */

function renderScreenLink() {
    const link = byId('screenLink');
    if (link) link.href = `/tournaments-afisha/${catalogState.entriesTournamentId}/screen`;
}

function statTableMarkup(title, headers, rows) {
    if (!rows.length) return '';
    return `
        <section class="stat-block">
            <h3>${escapeHtml(title)}</h3>
            <div class="table-wrap">
                <table class="stat-table">
                    <thead><tr>${headers.map((h) => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>
                    <tbody>${rows.join('')}</tbody>
                </table>
            </div>
        </section>`;
}

function playerCellMarkup(row) {
    return `<span class="stat-player">
        <span class="stat-photo"${row.photo_url
            ? ` style="background-image:url('${escapeHtml(row.photo_url)}')"` : ''}></span>
        <span>
            <strong>${escapeHtml(row.name)}</strong>
            <small>${escapeHtml(row.team_name)}</small>
        </span>
    </span>`;
}

/* --- Лидеры: бомбардиры, ассистенты, гол+пас, с картинками для соцсетей --- */

const LEADER_COLUMNS = [
    { key: 'goals', title: 'Бомбардиры', unit: 'голов', image: 'Goals' },
    { key: 'assists', title: 'Ассистенты', unit: 'передач', image: 'Assists' },
    { key: 'points', title: 'Гол + пас', unit: 'очков', image: 'Points' },
];

function leaderImageUrl(kind, limit) {
    return `/api/tournaments/${catalogState.entriesTournamentId}/leaders.png`
        + `?age_group=${encodeURIComponent(catalogState.playersAge)}&kind=${kind}&limit=${limit}&download=1`;
}

function renderLeaders() {
    const host = byId('leadersBoard');
    const leaders = catalogState.leaders;
    if (!host) return;
    const any = leaders && LEADER_COLUMNS.some((column) => (leaders[column.key] || []).length);
    if (!any) {
        host.innerHTML = leaders ? `
            <header class="leaders-head"><h3>Лидеры</h3></header>
            <p class="leaders-empty">Появятся, когда в матчах будут указаны авторы голов и передач
                (на вкладке «Турнир» нажмите на счёт матча).</p>` : '';
        return;
    }
    const limit = catalogState.leadersLimit || 5;
    host.innerHTML = `
        <header class="leaders-head">
            <h3>Лидеры</h3>
            <div class="leaders-tools">
                <div class="leaders-switch" role="group" aria-label="Сколько показать">
                    ${[5, 10].map((value) => `<button type="button" data-leaders-limit="${value}"
                        class="${value === limit ? 'active' : ''}">Топ-${value}</button>`).join('')}
                </div>
                <a class="btn-primary leaders-all" href="${leaderImageUrl('all', 10)}" download>
                    <i data-lucide="image-down"></i> Картинка: Goals · Assists · Points</a>
            </div>
        </header>
        <div class="leaders-grid">
            ${LEADER_COLUMNS.map((column) => {
                const rows = (leaders[column.key] || []).slice(0, limit);
                return `
                    <article class="leader-card">
                        <div class="leader-card-head">
                            <strong>${escapeHtml(column.title)}</strong>
                            ${rows.length ? `<a href="${leaderImageUrl(column.key, limit)}" download
                                title="Скачать картинку «Топ-${limit}. ${escapeHtml(column.title)}»">
                                <i data-lucide="download"></i> Топ-${limit}</a>` : ''}
                        </div>
                        <ol>
                            ${rows.map((row, index) => `
                                <li>
                                    <span class="leader-no">${index + 1}</span>
                                    <span class="leader-photo"${row.photo_url
                                        ? ` style="background-image:url('${escapeHtml(row.photo_url)}')"` : ''}>${row.photo_url
                                        ? '' : escapeHtml(initials(row.name))}</span>
                                    <span class="leader-info">
                                        <strong>${escapeHtml(row.name)}</strong>
                                        <small>${row.team_logo_url ? `<img src="${escapeHtml(row.team_logo_url)}" alt="">` : ''}${escapeHtml(row.team_name)}</small>
                                    </span>
                                    <b class="leader-value" title="${escapeHtml(column.unit)}">${row.value}</b>
                                </li>`).join('') || '<li class="leader-none">пока никого</li>'}
                        </ol>
                    </article>`;
            }).join('')}
        </div>`;
    refreshIcons();
}

function renderPlayers() {
    const board = byId('playersBoard');
    const stats = catalogState.playersStats;
    if (!stats) { board.innerHTML = ''; return; }
    const empty = !stats.scorers.length && !stats.goalkeepers.length && !stats.cards.length;
    if (empty) {
        board.innerHTML = emptyCatalogMarkup(
            'clipboard-list',
            'Протоколы ещё не заполнены',
            'На вкладке «Турнир» нажмите на счёт матча и укажите, кто забил.',
        );
        refreshIcons();
        return;
    }

    board.innerHTML = [
        statTableMarkup('Вратари',
            ['#', 'Вратарь', 'Матчи', 'Пропущено', 'В среднем', 'Сухие матчи'],
            stats.goalkeepers.map((row, index) => `
                <tr class="${row.qualified ? '' : 'stat-muted'}">
                    <td>${index + 1}</td><td>${playerCellMarkup(row)}</td>
                    <td>${row.matches}</td><td>${row.conceded}</td>
                    <td>${row.avg_conceded === null ? '—' : row.avg_conceded}</td>
                    <td><strong>${row.clean_sheets}</strong></td></tr>`)),
        statTableMarkup('Карточки',
            ['#', 'Игрок', 'Жёлтые', 'Красные'],
            stats.cards.map((row, index) => `
                <tr><td>${index + 1}</td><td>${playerCellMarkup(row)}</td>
                    <td>${row.yellow}</td><td>${row.red}</td></tr>`)),
        statTableMarkup('Fair Play',
            ['#', 'Команда', 'Матчи', 'Штрафные очки'],
            stats.fair_play.map((row, index) => `
                <tr><td>${index + 1}</td>
                    <td><span class="stat-player">
                        <span class="stat-photo round"${row.team_logo_url
                            ? ` style="background-image:url('${escapeHtml(row.team_logo_url)}')"` : ''}></span>
                        <span><strong>${escapeHtml(row.team_name)}</strong></span></span></td>
                    <td>${row.matches}</td><td><strong>${row.penalty}</strong></td></tr>`)),
    ].join('');
    refreshIcons();
}

function awardOptionsMarkup(award) {
    const stats = catalogState.playersStats;
    if (award.code === 'fair_play') {
        return ['<option value="">— не присуждена —</option>'].concat(
            (stats.fair_play || []).map((row) => `<option value="team:${row.entry_id}" ${
                award.winner && award.winner.team_name === row.team_name && !award.winner.member_id
                    ? 'selected' : ''}>${escapeHtml(row.team_name)}</option>`)).join('');
    }
    const seen = new Map();
    ['scorers', 'goalkeepers', 'cards'].forEach((key) => {
        (stats[key] || []).forEach((row) => seen.set(row.member_id, row));
    });
    const people = [...seen.values()].sort((a, b) => a.name.localeCompare(b.name, 'ru'));
    return ['<option value="">— не присуждена —</option>'].concat(
        people.map((row) => `<option value="member:${row.member_id}" ${
            award.winner && award.winner.member_id === row.member_id ? 'selected' : ''
        }>${escapeHtml(row.name)} · ${escapeHtml(row.team_name)}</option>`)).join('');
}

function awardFace(winner) {
    return winner.member_id ? winner.photo_url : winner.team_logo_url;
}

function renderAwards() {
    const board = byId('awardsBoard');
    const awards = catalogState.playersAwards;
    if (!awards.length) { board.innerHTML = ''; return; }
    board.innerHTML = `
        <section class="awards-block">
            <h3>Награды турнира</h3>
            <div class="awards-grid">
                ${awards.map((award) => `
                    <div class="award-card" data-award="${award.code}">
                        <p class="award-title">${escapeHtml(award.title)}
                            ${award.computed ? '<span class="award-auto">расчётная</span>' : ''}</p>
                        <div class="award-winner">
                            <span class="award-photo${award.winner && !award.winner.member_id ? ' round' : ''}"${
                                award.winner && awardFace(award.winner)
                                    ? ` style="background-image:url('${escapeHtml(
                                        awardFace(award.winner))}')"` : ''}></span>
                            <span>
                                <strong>${award.winner ? escapeHtml(award.winner.name) : 'не присуждена'}</strong>
                                <small>${award.winner ? escapeHtml(award.winner.team_name) : ''}</small>
                            </span>
                        </div>
                        ${award.suggested ? `<p class="award-hint">Система предлагает:
                            ${escapeHtml(award.suggested.name || award.suggested.team_name)}</p>` : ''}
                        <select data-award-select>${awardOptionsMarkup(award)}</select>
                        ${award.winner ? `<a class="award-cover"
                            href="/api/tournaments/${catalogState.entriesTournamentId}/awards/${award.code}`
                            + `/cover.png?age_group=${encodeURIComponent(catalogState.playersAge)}"
                            download><i data-lucide="image-down"></i> Обложка для соцсетей</a>` : ''}
                    </div>`).join('')}
            </div>
        </section>`;
    refreshIcons();
}

async function loadPlayers() {
    if (!catalogState.playersAge) {
        catalogState.playersStats = null;
        catalogState.playersAwards = [];
        catalogState.leaders = null;
        renderLeaders();
        renderPlayers();
        renderAwards();
        return;
    }
    try {
        showFormError('playersError');
        const data = await apiJson(
            `/api/tournaments/${catalogState.entriesTournamentId}/players`
            + `?age_group=${encodeURIComponent(catalogState.playersAge)}`,
        );
        catalogState.playersStats = data.stats;
        catalogState.playersAwards = data.awards || [];
        catalogState.leaders = data.leaders || null;
        renderLeaders();
        renderPlayers();
        renderAwards();
    } catch (error) {
        showFormError('playersError', error.message);
    }
}

async function saveAward(code, value) {
    const payload = { age_group: catalogState.playersAge, code };
    if (value.startsWith('member:')) payload.member_id = Number(value.slice(7));
    else if (value.startsWith('team:')) payload.entry_id = Number(value.slice(5));
    try {
        showFormError('playersError');
        const data = await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}/awards`, {
            method: 'PUT',
            body: JSON.stringify(payload),
        });
        if (data.awards) {
            catalogState.playersAwards = data.awards;
            renderAwards();
        } else {
            await loadPlayers();
        }
    } catch (error) {
        showFormError('playersError', error.message);
    }
}

/* --- Ссылка для тренера: заполнение состава команды --- */

function formatShareDeadline(value) {
    if (!value) return '';
    return new Intl.DateTimeFormat('ru-RU', {
        day: '2-digit', month: 'long', year: 'numeric', hour: '2-digit', minute: '2-digit',
    }).format(new Date(value));
}

function renderShareTournamentOptions(selectedId) {
    const select = byId('teamShareTournament');
    // Ссылка живёт до начала турнира, поэтому предлагаем только те, что ещё не начались.
    const now = new Date();
    const upcoming = catalogState.tournaments.filter((item) => {
        if (!item.start_date) return false;
        return new Date(`${item.start_date}T${item.start_time || '00:00'}`) > now;
    });
    const options = ['<option value="">Выберите турнир</option>'].concat(
        upcoming.map((item) => `
            <option value="${item.id}">${escapeHtml(item.name)} — ${formatDate(item.start_date)}</option>
        `),
    );
    select.innerHTML = options.join('');
    if (selectedId) select.value = String(selectedId);
    if (!upcoming.length) {
        showFormError('teamShareError', 'Нет предстоящих турниров — сначала создайте турнир с датой начала.');
    }
}

function renderShareLink() {
    const link = catalogState.shareLink;
    const result = byId('teamShareResult');
    byId('createTeamShareLink').textContent = link ? 'Сохранить срок' : 'Создать ссылку';
    if (!link) {
        result.hidden = true;
        return;
    }
    result.hidden = false;
    byId('teamShareLink').value = link.url;
    byId('openTeamShareLink').href = link.url;
    const status = byId('teamShareStatus');
    if (link.is_open) {
        status.className = 'team-share-status open';
        status.textContent = `Открыта до ${formatShareDeadline(link.deadline)} · ${link.tournament_name || ''}`;
    } else {
        status.className = 'team-share-status closed';
        status.textContent = 'Турнир начался — форма открывается только на чтение.';
    }
}

async function openTeamShare(teamId) {
    const team = catalogState.teams.find((item) => Number(item.id) === Number(teamId));
    if (!team) return;
    catalogState.shareTeamId = team.id;
    catalogState.shareLink = null;
    byId('teamShareTitle').textContent = `Поделиться · ${team.name}`;
    showFormError('teamShareError');
    byId('teamShareResult').hidden = true;
    openModal('teamShareModal');
    try {
        const data = await apiJson(`/api/tournament-team-catalog/${team.id}/share`);
        catalogState.shareLink = data.link || null;
    } catch (error) {
        showFormError('teamShareError', error.message);
    }
    renderShareTournamentOptions(catalogState.shareLink ? catalogState.shareLink.tournament_id : '');
    renderShareLink();
}

async function createTeamShareLink() {
    const teamId = catalogState.shareTeamId;
    const tournamentId = byId('teamShareTournament').value;
    if (!teamId) return;
    if (!tournamentId) {
        showFormError('teamShareError', 'Выберите турнир');
        return;
    }
    try {
        showFormError('teamShareError');
        const data = await apiJson(`/api/tournament-team-catalog/${teamId}/share`, {
            method: 'POST',
            body: JSON.stringify({ tournament_id: Number(tournamentId) }),
        });
        catalogState.shareLink = data.link;
        renderShareLink();
    } catch (error) {
        showFormError('teamShareError', error.message);
    }
}

async function revokeTeamShareLink() {
    const teamId = catalogState.shareTeamId;
    if (!teamId || !window.confirm('Закрыть доступ по ссылке? Тренер больше не сможет её открыть.')) return;
    try {
        showFormError('teamShareError');
        await apiJson(`/api/tournament-team-catalog/${teamId}/share`, { method: 'DELETE' });
        catalogState.shareLink = null;
        renderShareLink();
    } catch (error) {
        showFormError('teamShareError', error.message);
    }
}

async function copyTeamShareLink() {
    const input = byId('teamShareLink');
    const button = byId('copyTeamShareLink');
    try {
        await navigator.clipboard.writeText(input.value);
    } catch (error) {
        // Без защищённого контекста clipboard недоступен — выделяем текст вручную.
        input.select();
        document.execCommand('copy');
    }
    button.textContent = 'Скопировано';
    window.setTimeout(() => { button.textContent = 'Копировать'; }, 1600);
}

function resetStadiumForm() {
    catalogState.editingStadiumId = null;
    byId('stadiumForm').reset();
    byId('stadiumModalTitle').textContent = 'Новый стадион';
    byId('stadiumCoordinates').textContent = 'Нажмите на карту, чтобы поставить точку';
    releaseObjectUrl('stadiumPhotoObjectUrl');
    setPhotoPreview(
        'stadiumPhotoPreview',
        'stadiumPhotoFileName',
        '',
        'image-plus',
        'Необязательно · PNG, JPG или WEBP',
    );
    showFormError('stadiumFormError');
}

async function runStadiumImport() {
    const button = byId('runStadiumImport');
    button.disabled = true;
    button.textContent = 'Загружаем…';
    try {
        showFormError('stadiumImportError');
        const data = await apiJson('/api/tournament-stadiums/import-osm', {
            method: 'POST',
            body: JSON.stringify({ area: byId('stadiumImportArea').value }),
        });
        byId('stadiumImportResult').hidden = false;
        const parts = [];
        if (data.added) parts.push(`добавлено ${data.added}`);
        if (data.with_photo || data.enriched) {
            parts.push(`фото у ${(data.with_photo || 0) + (data.enriched || 0)}`);
        }
        if (data.skipped) parts.push(`пропущено как дубли ${data.skipped}`);
        byId('stadiumImportStatus').textContent = parts.length
            ? `${data.area}: ${parts.join(', ')}`
            : `${data.area}: новых стадионов не нашлось (проверено ${data.found})`;
        await loadStadiums();
    } catch (error) {
        showFormError('stadiumImportError', error.message);
    } finally {
        button.disabled = false;
        button.textContent = 'Импортировать';
    }
}

function openStadiumCreator(options = {}) {
    catalogState.stadiumReturnToTournament = Boolean(options.returnToTournament);
    resetStadiumForm();
    openModal('stadiumModal');
    ensureStadiumMap();
}

function openStadiumEditor(id) {
    const stadium = catalogState.stadiums.find((item) => Number(item.id) === Number(id));
    if (!stadium) return;
    catalogState.editingStadiumId = stadium.id;
    catalogState.stadiumReturnToTournament = false;
    byId('stadiumModalTitle').textContent = 'Редактировать стадион';
    byId('stadiumName').value = stadium.name || '';
    byId('stadiumOwnerPhone').value = stadium.owner_phone || '';
    byId('stadiumLength').value = stadium.length || '';
    byId('stadiumWidth').value = stadium.width || '';
    releaseObjectUrl('stadiumPhotoObjectUrl');
    setPhotoPreview(
        'stadiumPhotoPreview',
        'stadiumPhotoFileName',
        stadium.photo_url || '',
        'image-plus',
        stadium.photo_url ? 'Текущее фото стадиона' : 'Необязательно · PNG, JPG или WEBP',
    );
    showFormError('stadiumFormError');
    openModal('stadiumModal');
    ensureStadiumMap(stadium.latitude, stadium.longitude, true);
}

async function saveStadium(event) {
    event.preventDefault();
    const editingId = catalogState.editingStadiumId;
    const formData = new FormData();
    formData.append('name', byId('stadiumName').value);
    formData.append('owner_phone', byId('stadiumOwnerPhone').value);
    formData.append('length', byId('stadiumLength').value);
    formData.append('width', byId('stadiumWidth').value);
    formData.append('latitude', byId('stadiumLatitude').value);
    formData.append('longitude', byId('stadiumLongitude').value);
    const photo = byId('stadiumPhoto').files[0];
    if (photo) formData.append('photo', photo);
    try {
        showFormError('stadiumFormError');
        const result = await apiJson(
            editingId ? `/api/tournament-stadiums/${editingId}` : '/api/tournament-stadiums',
            { method: editingId ? 'PUT' : 'POST', body: formData },
        );
        const returnToTournament = catalogState.stadiumReturnToTournament;
        const savedName = result && result.stadium ? result.stadium.name : '';
        closeModal('stadiumModal');
        resetStadiumForm();
        await loadStadiums();
        // Окно турнира оставалось открытым — сразу выбираем созданный стадион.
        if (returnToTournament && savedName) renderStadiumOptions(savedName);
    } catch (error) {
        showFormError('stadiumFormError', error.message);
    }
}

async function deleteStadium(id) {
    const stadium = catalogState.stadiums.find((item) => Number(item.id) === Number(id));
    if (!stadium || !window.confirm(`Удалить стадион «${stadium.name}»?`)) return;
    await apiJson(`/api/tournament-stadiums/${id}`, { method: 'DELETE' });
    await loadStadiums();
}

function renderCatalogTab(tabName) {
    if (tabName === 'tournaments') renderTournaments();
    if (tabName === 'teams') renderTeams();
    if (tabName === 'stadiums') renderStadiums();
}

function hasActiveCatalogFilter(tabName) {
    const filter = catalogState.filters[tabName];
    if (tabName === 'tournaments') return Boolean(filter.location || filter.age);
    if (tabName === 'teams') return Boolean(filter.trainer || filter.minMembers !== '');
    if (tabName === 'stadiums') return Boolean(filter.phone);
    return false;
}

function updateFilterIndicator(tabName) {
    const indicator = document.querySelector(`[data-filter-indicator="${tabName}"]`);
    if (indicator) indicator.hidden = !hasActiveCatalogFilter(tabName);
}

function openCatalogFilter(tabName) {
    catalogState.activeFilterTab = tabName;
    const titles = {
        tournaments: 'Фильтр турниров',
        teams: 'Фильтр команд',
        stadiums: 'Фильтр стадионов',
    };
    byId('catalogFilterTitle').textContent = titles[tabName] || 'Фильтр';
    document.querySelectorAll('[data-filter-fields]').forEach((section) => {
        section.hidden = section.dataset.filterFields !== tabName;
    });

    const filter = catalogState.filters[tabName];
    if (tabName === 'tournaments') {
        byId('filterTournamentLocation').value = filter.location;
        byId('filterTournamentAge').value = filter.age;
    }
    if (tabName === 'teams') {
        byId('filterTeamTrainer').value = filter.trainer;
        byId('filterTeamMinMembers').value = filter.minMembers;
    }
    if (tabName === 'stadiums') {
        byId('filterStadiumPhone').value = filter.phone;
    }
    openModal('catalogFilterModal');
}

function applyCatalogFilter(event) {
    event.preventDefault();
    const tabName = catalogState.activeFilterTab;
    if (tabName === 'tournaments') {
        catalogState.filters.tournaments.location = byId('filterTournamentLocation').value.trim();
        catalogState.filters.tournaments.age = byId('filterTournamentAge').value.trim();
    }
    if (tabName === 'teams') {
        catalogState.filters.teams.trainer = byId('filterTeamTrainer').value.trim();
        catalogState.filters.teams.minMembers = byId('filterTeamMinMembers').value;
    }
    if (tabName === 'stadiums') {
        catalogState.filters.stadiums.phone = byId('filterStadiumPhone').value.trim();
    }
    updateFilterIndicator(tabName);
    renderCatalogTab(tabName);
    closeModal('catalogFilterModal');
}

function resetCatalogFilter() {
    const tabName = catalogState.activeFilterTab;
    if (tabName === 'tournaments') {
        catalogState.filters.tournaments.location = '';
        catalogState.filters.tournaments.age = '';
    }
    if (tabName === 'teams') {
        catalogState.filters.teams.trainer = '';
        catalogState.filters.teams.minMembers = '';
    }
    if (tabName === 'stadiums') {
        catalogState.filters.stadiums.phone = '';
    }
    updateFilterIndicator(tabName);
    renderCatalogTab(tabName);
    closeModal('catalogFilterModal');
}

function switchTab(tabName) {
    document.querySelectorAll('[data-catalog-tab]').forEach((button) => {
        const isActive = button.dataset.catalogTab === tabName;
        button.classList.toggle('active', isActive);
        button.setAttribute('aria-selected', String(isActive));
    });
    document.querySelectorAll('.tournament-catalog-panel').forEach((panel) => {
        panel.classList.toggle('active', panel.id === `catalogPanel-${tabName}`);
    });
    document.querySelectorAll('.team-actions-menu[open]').forEach((menu) => menu.removeAttribute('open'));
}

function bindEvents() {
    document.querySelectorAll('[data-catalog-tab]').forEach((button) => {
        button.addEventListener('click', () => switchTab(button.dataset.catalogTab));
    });
    document.querySelectorAll('[data-close-modal]').forEach((button) => {
        button.addEventListener('click', () => closeModal(button.dataset.closeModal));
    });
    document.querySelectorAll('[data-catalog-search]').forEach((input) => {
        input.addEventListener('input', () => {
            const tabName = input.dataset.catalogSearch;
            catalogState.filters[tabName].search = input.value;
            renderCatalogTab(tabName);
        });
    });
    document.querySelectorAll('[data-open-filter]').forEach((button) => {
        button.addEventListener('click', () => openCatalogFilter(button.dataset.openFilter));
    });
    document.querySelectorAll('.tournament-catalog-modal').forEach((modal) => {
        modal.addEventListener('click', (event) => {
            if (event.target === modal) closeModal(modal.id);
        });
    });
    byId('openTournamentModalBtn').addEventListener('click', () => {
        resetTournamentForm();
        openModal('tournamentModal');
    });
    byId('openTeamModalBtn').addEventListener('click', () => {
        resetTeamForm();
        openModal('teamModal');
    });
    byId('openStadiumModalBtn').addEventListener('click', () => openStadiumCreator());
    byId('openStadiumImportBtn').addEventListener('click', () => {
        showFormError('stadiumImportError');
        byId('stadiumImportResult').hidden = true;
        openModal('stadiumImportModal');
    });
    byId('runStadiumImport').addEventListener('click', runStadiumImport);
    byId('openMemberModalBtn').addEventListener('click', () => {
        resetMemberForm();
        openModal('memberModal');
    });
    byId('tournamentPoster').addEventListener('change', () => {
        const file = byId('tournamentPoster').files[0];
        releaseTournamentPoster();
        if (!file) {
            setTournamentPoster('');
            return;
        }
        catalogState.tournamentPosterRemoved = false;
        catalogState.tournamentPosterObjectUrl = URL.createObjectURL(file);
        setTournamentPoster(catalogState.tournamentPosterObjectUrl, file.name);
    });
    byId('tournamentPosterClear').addEventListener('click', (event) => {
        // Слот — это <label>, поэтому крестик не должен открывать выбор файла.
        event.preventDefault();
        event.stopPropagation();
        releaseTournamentPoster();
        byId('tournamentPoster').value = '';
        catalogState.tournamentPosterRemoved = true;
        setTournamentPoster('');
    });
    byId('tournamentLocation').addEventListener('change', handleTournamentLocationChange);
    byId('tournamentAgeGroupYear').addEventListener('change', (event) => {
        addAgeGroup(event.target.value);
        event.target.value = '';
    });
    byId('tournamentAgeGroupAdd').addEventListener('click', addCustomAgeGroup);
    byId('tournamentAgeGroupCustom').addEventListener('keydown', (event) => {
        if (event.key !== 'Enter') return;
        event.preventDefault();
        addCustomAgeGroup();
    });
    byId('tournamentAgeGroupChips').addEventListener('click', (event) => {
        const button = event.target.closest('[data-remove-age-group]');
        if (button) removeAgeGroup(button.dataset.removeAgeGroup);
    });
    byId('tournamentForm').addEventListener('submit', saveTournament);
    byId('teamForm').addEventListener('submit', saveTeam);
    byId('memberForm').addEventListener('submit', saveMember);
    byId('stadiumForm').addEventListener('submit', saveStadium);
    document.querySelectorAll('[data-entry-tab]').forEach((button) => {
        button.addEventListener('click', () => {
            switchEntryTab(button.dataset.entryTab);
            renderSteps();
            if (button.dataset.entryTab === 'players') loadPlayers();
        });
    });
    byId('categorySwitch').addEventListener('click', (event) => {
        const button = event.target.closest('[data-category]');
        if (button) switchCategory(button.dataset.category).catch(showPageError);
    });
    byId('tournamentEntriesModal').addEventListener('change', (event) => {
        const select = event.target.closest('[data-tiebreak-select]');
        if (select) setTiebreak(select.value);
    });
    byId('runScheduleBtn').addEventListener('click', () => runSchedule().catch(showPageError));
    byId('leadersBoard').addEventListener('click', (event) => {
        const button = event.target.closest('[data-leaders-limit]');
        if (!button) return;
        catalogState.leadersLimit = Number(button.dataset.leadersLimit);
        renderLeaders();
    });
    byId('awardsBoard').addEventListener('change', (event) => {
        const select = event.target.closest('[data-award-select]');
        if (!select) return;
        const card = select.closest('[data-award]');
        saveAward(card.dataset.award, select.value).catch(showPageError);
    });
    byId('saveProtocolBtn').addEventListener('click', () => saveProtocol().catch(showPageError));
    byId('openStudioBtn').addEventListener('click', () => openStudio({
        age_group: catalogState.age,
    }));
    byId('studioDownload').addEventListener('click', downloadStudio);
    byId('studioUpload').addEventListener('change', (event) => {
        const file = event.target.files && event.target.files[0];
        if (file) uploadStudioBackground(file);
    });
    byId('postStudioModal').addEventListener('click', (event) => {
        const template = event.target.closest('[data-template]');
        if (template) {
            studio.template = template.dataset.template;
            document.querySelectorAll('#studioTemplates .studio-chip').forEach((chip) =>
                chip.classList.toggle('active', chip.dataset.template === studio.template));
            renderStudioSource();
            renderStudio();
            return;
        }
        const background = event.target.closest('[data-background]');
        if (background) {
            studio.background = background.dataset.background;
            document.querySelectorAll('#studioBackgrounds .studio-chip').forEach((chip) =>
                chip.classList.toggle('active', chip.dataset.background === studio.background));
            byId('studioShadeRow').hidden = studio.background === 'none';
            byId('studioUploadField').hidden = studio.background !== 'custom';
            renderStudio();
            return;
        }
        const swatch = event.target.closest('[data-accent]');
        if (swatch) {
            studio.accent = swatch.dataset.accent;
            document.querySelectorAll('.studio-swatch').forEach((item) =>
                item.classList.toggle('active', item.dataset.accent === studio.accent));
            renderStudio();
        }
    });
    byId('postStudioModal').addEventListener('input', (event) => {
        if (event.target.id === 'studioAccentPicker') {
            studio.accent = event.target.value;
            document.querySelectorAll('.studio-swatch').forEach((item) =>
                item.classList.remove('active'));
        }
        if (event.target.matches('input[type="text"], input[type="range"], #studioAccentPicker')) {
            scheduleStudio();
        }
    });
    byId('postStudioModal').addEventListener('change', (event) => {
        if (event.target.id === 'studioAge') renderStudioSource();
        if (event.target.matches('select, input[type="checkbox"]')) renderStudio();
    });
    byId('matchProtocolModal').addEventListener('click', (event) => {
        if (event.target.closest('[data-close-protocol]')) {
            closeModal('matchProtocolModal');
            return;
        }
        const gk = event.target.closest('[data-gk]');
        if (gk) {
            // Вратарь в команде один: отмечая нового, снимаем прежнего.
            event.preventDefault();
            const team = gk.closest('.protocol-team');
            const was = gk.classList.contains('on');
            team.querySelectorAll('[data-gk]').forEach((item) => item.classList.remove('on'));
            if (!was) {
                gk.classList.add('on');
                const box = gk.closest('.protocol-player').querySelector('[data-play]');
                if (!box.checked) {
                    box.checked = true;
                    box.closest('.protocol-player').classList.add('on');
                }
            }
            renderProtocolEvents();
            return;
        }
        const add = event.target.closest('[data-add-event]');
        if (add) {
            catalogState.protocolEvents.push({
                side: 'home',
                kind: add.dataset.addEvent,
                member_id: null,
                assist_member_id: null,
                minute: null,
                is_own_goal: false,
                is_penalty: false,
                card: add.dataset.addEvent === 'card' ? 'yellow' : null,
            });
            renderProtocolEvents();
            return;
        }
        const remove = event.target.closest('[data-remove-event]');
        if (remove) {
            catalogState.protocolEvents.splice(Number(remove.closest('.protocol-event').dataset.index), 1);
            renderProtocolEvents();
        }
    });
    byId('matchProtocolModal').addEventListener('change', (event) => {
        const player = event.target.closest('[data-play]');
        if (player) {
            const row = player.closest('.protocol-player');
            row.classList.toggle('on', player.checked);
            if (!player.checked) row.querySelector('[data-gk]').classList.remove('on');
            const team = row.closest('.protocol-team');
            team.querySelector('[data-count]').textContent =
                team.querySelectorAll('[data-play]:checked').length;
            renderProtocolEvents();
            return;
        }
        const field = event.target.closest('[data-field]');
        if (!field) return;
        const row = field.closest('.protocol-event');
        const item = catalogState.protocolEvents[Number(row.dataset.index)];
        const name = field.dataset.field;
        if (field.type === 'checkbox') item[name] = field.checked;
        else if (name === 'minute') item[name] = field.value === '' ? null : Number(field.value);
        else if (name === 'member_id' || name === 'assist_member_id') {
            item[name] = field.value ? Number(field.value) : null;
        } else item[name] = field.value;
        // Смена стороны или автогола меняет список игроков в строке.
        if (name === 'side' || name === 'is_own_goal') {
            item.member_id = null;
            item.assist_member_id = null;
        }
        renderProtocolEvents();
    });
    byId('entryTeamInput').addEventListener('focus', openTeamPicker);
    byId('entryTeamInput').addEventListener('input', openTeamPicker);
    byId('entryTeamInput').addEventListener('keydown', (event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
            event.preventDefault();
            if (byId('entryTeamList').hidden) openTeamPicker();
            moveTeamHighlight(event.key === 'ArrowDown' ? 1 : -1);
            return;
        }
        if (event.key === 'Enter') {
            const teams = filteredPickerTeams();
            const team = teams[catalogState.entryTeamHighlight] || (teams.length === 1 ? teams[0] : null);
            if (team) {
                event.preventDefault();
                pickTeam(team.id);
            }
            return;
        }
        if (event.key === 'Escape') {
            closeTeamPicker();
            return;
        }
        if (event.key === 'Backspace' && !event.target.value && catalogState.entryTeamIds.length) {
            dropTeamChip(catalogState.entryTeamIds[catalogState.entryTeamIds.length - 1]);
        }
    });
    byId('entryTeamBox').addEventListener('click', (event) => {
        const drop = event.target.closest('[data-drop-team]');
        if (drop) {
            event.preventDefault();
            dropTeamChip(drop.dataset.dropTeam);
            return;
        }
        byId('entryTeamInput').focus();
    });
    byId('entryAgeChips').addEventListener('change', () => {
        catalogState.entryAges = selectedEntryAges();
        document.querySelectorAll('#entryAgeChips .age-pick').forEach((chip) =>
            chip.classList.toggle('on', chip.querySelector('input').checked));
        if (!byId('entryTeamList').hidden) renderTeamPickerList();
    });
    byId('entryTeamList').addEventListener('mousedown', (event) => {
        // mousedown, а не click: до click поле теряет фокус и список успевает закрыться.
        const option = event.target.closest('[data-pick-team]');
        if (!option) return;
        event.preventDefault();
        pickTeam(option.dataset.pickTeam);
    });
    document.addEventListener('click', (event) => {
        if (!event.target.closest('#entryTeamPicker')) closeTeamPicker();
    });
    byId('addEntryBtn').addEventListener('click', () => addTournamentEntry().catch(showPageError));
    byId('entriesList').addEventListener('change', (event) => {
        const select = event.target.closest('[data-entry-status]');
        if (select) updateEntryStatus(select.dataset.entryStatus, select.value).catch(showPageError);
    });
    bindRosterModal();
    byId('entriesList').addEventListener('click', (event) => {
        const roster = event.target.closest('[data-roster-team]');
        if (roster) {
            openRoster(roster.dataset.rosterTeam).catch(showPageError);
            return;
        }
        const button = event.target.closest('[data-delete-entry]');
        if (button) deleteTournamentEntry(button.dataset.deleteEntry).catch(showPageError);
    });
    byId('createTeamShareLink').addEventListener('click', createTeamShareLink);
    byId('revokeTeamShareLink').addEventListener('click', revokeTeamShareLink);
    byId('copyTeamShareLink').addEventListener('click', copyTeamShareLink);
    byId('catalogFilterForm').addEventListener('submit', applyCatalogFilter);
    byId('resetCatalogFilterBtn').addEventListener('click', resetCatalogFilter);
    byId('teamLogo').addEventListener('change', () => {
        const file = byId('teamLogo').files[0];
        if (!file) {
            setTeamLogoPreview();
            return;
        }
        releaseTeamLogoPreview();
        catalogState.teamLogoObjectUrl = URL.createObjectURL(file);
        byId('teamLogoPreview').innerHTML = `<img src="${catalogState.teamLogoObjectUrl}" alt="">`;
        byId('teamLogoFileName').textContent = file.name;
    });
    byId('teamTrainerPhoto').addEventListener('change', () => {
        const file = byId('teamTrainerPhoto').files[0];
        releaseObjectUrl('trainerPhotoObjectUrl');
        if (!file) {
            setPhotoPreview(
                'trainerPhotoPreview',
                'trainerPhotoFileName',
                '',
                'user-round',
                'Необязательно · PNG, JPG или WEBP',
            );
            return;
        }
        catalogState.trainerPhotoObjectUrl = URL.createObjectURL(file);
        setPhotoPreview(
            'trainerPhotoPreview',
            'trainerPhotoFileName',
            catalogState.trainerPhotoObjectUrl,
            'user-round',
            file.name,
        );
    });
    byId('memberPhoto').addEventListener('change', () => {
        const file = byId('memberPhoto').files[0];
        releaseObjectUrl('memberPhotoObjectUrl');
        if (!file) {
            setPhotoPreview('memberPhotoPreview', 'memberPhotoFileName', '', 'user-round-plus');
            return;
        }
        catalogState.memberPhotoObjectUrl = URL.createObjectURL(file);
        setPhotoPreview(
            'memberPhotoPreview',
            'memberPhotoFileName',
            catalogState.memberPhotoObjectUrl,
            'user-round-plus',
            file.name,
        );
    });
    byId('stadiumPhoto').addEventListener('change', () => {
        const file = byId('stadiumPhoto').files[0];
        releaseObjectUrl('stadiumPhotoObjectUrl');
        if (!file) {
            setPhotoPreview(
                'stadiumPhotoPreview',
                'stadiumPhotoFileName',
                '',
                'image-plus',
                'Необязательно · PNG, JPG или WEBP',
            );
            return;
        }
        catalogState.stadiumPhotoObjectUrl = URL.createObjectURL(file);
        setPhotoPreview(
            'stadiumPhotoPreview',
            'stadiumPhotoFileName',
            catalogState.stadiumPhotoObjectUrl,
            'image-plus',
            file.name,
        );
    });
    byId('memberBirthDate').addEventListener('input', (event) => {
        const digits = event.target.value.replace(/\D/g, '').slice(0, 8);
        event.target.value = [
            digits.slice(0, 2),
            digits.slice(2, 4),
            digits.slice(4, 8),
        ].filter(Boolean).join('.');
    });
    byId('tournamentList').addEventListener('click', (event) => {
        const openButton = event.target.closest('[data-open-tournament]');
        if (openButton) {
            openTournamentEntries(openButton.dataset.openTournament).catch(showPageError);
            return;
        }
        const entriesButton = event.target.closest('[data-entries-tournament]');
        if (entriesButton) {
            entriesButton.closest('details')?.removeAttribute('open');
            openTournamentEntries(entriesButton.dataset.entriesTournament).catch(showPageError);
            return;
        }
        const editButton = event.target.closest('[data-edit-tournament]');
        const deleteButton = event.target.closest('[data-delete-tournament]');
        if (editButton) openTournamentEditor(editButton.dataset.editTournament);
        if (deleteButton) deleteTournament(deleteButton.dataset.deleteTournament).catch(showPageError);
        if (editButton || deleteButton) return;
        // Клик в любом месте строки (кроме меню ⋮) открывает турнир.
        const row = event.target.closest('[data-row-tournament]');
        if (row && !event.target.closest('.catalog-actions-cell, details')) {
            openTournamentEntries(row.dataset.rowTournament).catch(showPageError);
        }
    });
    byId('teamList').addEventListener('click', (event) => {
        const menu = event.target.closest('.team-actions-menu');
        const menuSummary = event.target.closest('.team-actions-menu > summary');
        if (menuSummary) {
            document.querySelectorAll('.team-actions-menu[open]').forEach((item) => {
                if (item !== menu) item.removeAttribute('open');
            });
            return;
        }
        const shareButton = event.target.closest('[data-share-team]');
        const editButton = event.target.closest('[data-edit-team]');
        const deleteButton = event.target.closest('[data-delete-team]');
        if (shareButton) {
            menu?.removeAttribute('open');
            openTeamShare(shareButton.dataset.shareTeam).catch(showPageError);
            return;
        }
        if (editButton) {
            menu?.removeAttribute('open');
            openTeamEditor(editButton.dataset.editTeam);
            return;
        }
        if (deleteButton) {
            menu?.removeAttribute('open');
            deleteTeam(deleteButton.dataset.deleteTeam).catch(showPageError);
            return;
        }
        const openButton = event.target.closest('[data-open-team]');
        if (openButton) openTeamDetails(openButton.dataset.openTeam).catch(showPageError);
    });
    document.addEventListener('click', (event) => {
        const menu = event.target.closest('.team-actions-menu');
        const summary = event.target.closest('.team-actions-menu > summary');
        if (summary) {
            document.querySelectorAll('.team-actions-menu[open]').forEach((item) => {
                if (item !== menu) item.removeAttribute('open');
            });
            return;
        }
        if (menu) return;
        document.querySelectorAll('.team-actions-menu[open]').forEach((menu) => {
            menu.removeAttribute('open');
        });
    });
    byId('teamMembersTableBody').addEventListener('click', (event) => {
        const editButton = event.target.closest('[data-edit-member]');
        const deleteButton = event.target.closest('[data-delete-member]');
        if (editButton) openMemberEditor(editButton.dataset.editMember).catch(showPageError);
        if (deleteButton) deleteMember(deleteButton.dataset.deleteMember).catch(showPageError);
    });
    byId('stadiumList').addEventListener('click', (event) => {
        const editButton = event.target.closest('[data-edit-stadium]');
        const deleteButton = event.target.closest('[data-delete-stadium]');
        if (editButton) openStadiumEditor(editButton.dataset.editStadium);
        if (deleteButton) deleteStadium(deleteButton.dataset.deleteStadium).catch(showPageError);
    });
}

function showPageError(error) {
    window.alert(error.message || 'Не удалось выполнить действие');
}

document.addEventListener('DOMContentLoaded', async () => {
    bindEvents();
    renderAgeGroupYearOptions();
    setAgeGroups([]);
    refreshIcons();
    try {
        await Promise.all([loadTournaments(), loadTeams(), loadStadiums()]);
    } catch (error) {
        showPageError(error);
    }
});
