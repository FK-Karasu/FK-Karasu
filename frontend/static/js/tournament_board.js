/* Интерактивный вид турнира: шаблоны, ячейки групп, шахматка и сетка на одном полотне.
 *
 * Работает поверх tournaments.js и тех же данных (/category). Пошаговый вид не трогает:
 * если режим не приживётся, достаточно убрать этот файл и переключатель вида.
 */
(() => {
    const board = { reveal: false, popoverMatch: null };

    /* --- Шаблоны под число команд --- */

    function nextPow2(value) {
        let size = 1;
        while (size < value) size *= 2;
        return size;
    }

    // Как placement_layout на сервере: при двух группах — крест-накрест по 4 матча.
    function placementCount(sizes, advance) {
        let total = 0;
        let level = advance + 1;
        while (level <= Math.max(...sizes)) {
            const teams = sizes.filter((size) => size >= level).length;
            const next = sizes.filter((size) => size >= level + 1).length;
            if (sizes.length === 2 && teams === 2 && next === 2) {
                total += 4;
                level += 2;
            } else {
                total += Math.floor(teams / 2);
                level += 1;
            }
        }
        return total;
    }

    function templatesFor(count, withPlacement = true) {
        const list = [];
        if (count < 2) return list;
        const rr = (size) => (size * (size - 1)) / 2;
        list.push({
            key: 'league',
            settings: { format: 'league', groups: 1 },
            title: 'Круговой',
            sub: `все со всеми · ${pluralizeMatches(rr(count))}`,
        });
        [2, 3, 4, 6, 8].forEach((groups) => {
            if (Math.floor(count / groups) < 3) return;
            const sizes = splitSizes(count, groups);
            const advance = groups * 2 > 16 ? 1 : 2;
            const qualified = groups * advance;
            const matches = sizes.reduce((sum, size) => sum + rr(size), 0) + qualified - 1 + (qualified >= 4 ? 1 : 0)
                + (withPlacement ? placementCount(sizes, advance) : 0);
            const min = Math.min(...sizes);
            const max = Math.max(...sizes);
            list.push({
                key: `g${groups}`,
                settings: { format: 'groups_playoff', groups, advance },
                title: `${groups} гр. по ${min === max ? min : `${min}–${max}`}`,
                sub: `→ ${roundName(nextPow2(qualified) / 2)} · ${pluralizeMatches(matches)}`,
            });
        });
        list.push({
            key: 'knockout',
            settings: { format: 'knockout' },
            title: 'На вылет',
            sub: `с ${roundName(nextPow2(count) / 2)} · ${pluralizeMatches(count - 1 + (count >= 4 ? 1 : 0))}`,
        });
        return list;
    }

    const TEMPLATE_ART = {
        league: '/static/img/tournament/format-league.webp',
        groups: '/static/img/tournament/format-groups.webp',
        knockout: '/static/img/tournament/format-knockout.webp',
    };

    function templateArt(key) {
        if (key === 'league' || key === 'knockout') return TEMPLATE_ART[key];
        return TEMPLATE_ART.groups;
    }

    function logoMarkup(name, url) {
        return `<span class="board-logo">${url
            ? `<img src="${escapeHtml(url)}" alt="">` : escapeHtml(initials(name))}</span>`;
    }

    function activeTemplateKey(data) {
        const settings = data?.settings;
        if (!settings) return '';
        // Настройка по умолчанию ещё не выбор: шаблон «выбран», когда есть его ячейки или сетка.
        if (settings.format === 'knockout') return data.built ? 'knockout' : '';
        if (!data.groups.length) return '';
        if (settings.format === 'league') return 'league';
        return `g${data.groups.length}`;
    }

    async function applyTemplate(template) {
        const data = categoryOverview();
        if (data?.built && !window.confirm('Календарь будет удалён, команды останутся в своих ячейках, '
            + 'если группа сохранится. Продолжить?')) return;
        try {
            showFormError('boardError');
            await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}/template`, {
                method: 'POST',
                body: JSON.stringify({
                    age_group: catalogState.age,
                    settings: { ...(data?.settings || {}), third_place: true, ...template.settings },
                }),
            });
            catalogState.formatDirty = false;
            await loadCategory();
        } catch (error) {
            showFormError('boardError', error.message);
        }
    }

    /* --- Ячейки групп --- */

    function teamChip(entry, extraClass = '') {
        return `
            <span class="board-team ${extraClass}" data-board-entry="${entry.id}">
                <span class="board-logo">${entry.team_logo_url
                    ? `<img src="${escapeHtml(entry.team_logo_url)}" alt="">`
                    : escapeHtml(initials(entry.team_name))}</span>
                <span class="board-team-name">${escapeHtml(entry.team_name)}</span>
            </span>`;
    }

    function groupCellsMarkup(group, index, entries, capacity, locked) {
        const members = entries.filter((entry) => entry.group_id === group.id);
        const maxSlot = Math.max(capacity, ...members.map((entry) => entry.group_slot || 0), 0);
        const cells = [];
        let order = 0;
        for (let slot = 1; slot <= maxSlot; slot += 1) {
            const entry = members.find((item) => item.group_slot === slot);
            const code = `${group.name}${slot}`;
            if (entry) order += 1;
            cells.push(`
                <div class="board-cell${entry ? ' filled' : ''}" data-cell data-group-index="${index}" data-slot="${slot}"
                    style="--reveal:${(slot - 1) * 4 + index}">
                    <span class="board-code">${escapeHtml(code)}</span>
                    ${entry ? teamChip(entry, locked ? 'locked' : '') : '<span class="board-empty">пусто</span>'}
                </div>`);
        }
        return cells.join('');
    }

    function standingsByEntry(block) {
        const map = new Map();
        (block?.standings || []).forEach((row) => map.set(row.entry_id, row));
        return map;
    }

    function matrixMarkup(group, block, entries) {
        if (!block || !block.matches.length) return '';
        const rows = standingsByEntry(block);
        const started = (block.standings || []).some((row) => row.played > 0);
        // Как только сыграны матчи — строки по месту (1-е сверху), до этого — по ячейкам.
        // Столбцы в том же порядке, поэтому диагональ остаётся на месте.
        const members = entries.filter((entry) => entry.group_id === group.id)
            .sort((a, b) => (started
                ? (rows.get(a.id)?.place || 99) - (rows.get(b.id)?.place || 99)
                : (a.group_slot || 99) - (b.group_slot || 99)));
        if (members.length < 2) return '';
        const advance = categoryOverview()?.settings?.format === 'groups_playoff'
            ? categoryOverview().settings.advance : 0;
        const head = members.map((entry) => `<th title="${escapeHtml(entry.team_name)}"><span class="mx-head">${logoMarkup(entry.team_name, entry.team_logo_url)}</span></th>`).join('');
        const body = members.map((rowEntry) => {
            const stat = rows.get(rowEntry.id);
            const cells = members.map((colEntry) => {
                if (colEntry.id === rowEntry.id) return '<td class="mx-self"></td>';
                const pair = block.matches.filter((match) =>
                    (match.home.entry_id === rowEntry.id && match.away.entry_id === colEntry.id)
                    || (match.home.entry_id === colEntry.id && match.away.entry_id === rowEntry.id));
                return `<td class="mx-cell">${pair.map((match) => {
                    if (!match.is_played) {
                        return `<button type="button" class="mx-score todo" data-board-match="${match.id}"
                            title="${escapeHtml(`${match.home.team_name} — ${match.away.team_name}`)}">+</button>`;
                    }
                    const mine = match.home.entry_id === rowEntry.id ? match.home_score : match.away_score;
                    const theirs = match.home.entry_id === rowEntry.id ? match.away_score : match.home_score;
                    const result = mine > theirs ? 'w' : mine < theirs ? 'l' : 'd';
                    return `<button type="button" class="mx-score ${result}" data-board-match="${match.id}"
                        title="${escapeHtml(`${match.home.team_name} ${match.home_score}:${match.away_score} ${match.away.team_name}`)}">${mine}:${theirs}</button>`;
                }).join('')}</td>`;
            }).join('');
            // До первого сыгранного матча места нет — иначе это был бы просто алфавит.
            const place = started ? stat?.place : null;
            return `
                <tr class="${advance && block.finished && place <= advance ? 'mx-qualified' : ''}">
                    <th class="mx-team"><span class="mx-team-cell">${logoMarkup(rowEntry.team_name, rowEntry.team_logo_url)}<span class="mx-team-name">${escapeHtml(rowEntry.team_name)}</span></span></th>
                    ${cells}
                    <td class="mx-num">${stat ? stat.played : 0}</td>
                    <td class="mx-num">${stat ? `${stat.diff > 0 ? '+' : ''}${stat.diff}` : 0}</td>
                    <td class="mx-num mx-points">${stat ? stat.points : 0}</td>
                    <td class="mx-num"><span class="place-badge">${place || '—'}</span></td>
                </tr>`;
        }).join('');
        return `
            <div class="mx-wrap">
                <table class="mx-table">
                    <thead><tr><th></th>${head}<th title="Игры">И</th><th title="Разница мячей">±</th>
                        <th title="Очки">О</th><th title="Место в группе">Место</th></tr></thead>
                    <tbody>${body}</tbody>
                </table>
                ${tiebreakNoteMarkup()}
            </div>`;
    }

    function renderGroupsBoard(data) {
        const host = byId('boardGroups');
        const pool = byId('boardPool');
        const format = data.settings.format;
        const entries = data.entries || [];
        const locked = Boolean(data.has_results);
        const free = entries.filter((entry) => !entry.group_id);

        if (format === 'knockout') {
            host.innerHTML = '';
            pool.hidden = true;
            return;
        }
        pool.hidden = !free.length && !(!data.groups.length && entries.length);
        pool.innerHTML = `
            <span class="board-pool-title">${data.groups.length ? 'Без места' : 'Команды'}
                <small>${free.length ? 'перетащите в ячейку' : ''}</small></span>
            <div class="board-pool-list">${free.map((entry) => teamChip(entry)).join('')
                || '<span class="board-empty">все команды на местах</span>'}</div>`;

        if (!data.groups.length) {
            host.innerHTML = entries.length < 2
                ? emptyCatalogMarkup('users-round', 'Мало команд',
                    'Подтвердите хотя бы 2 команды — в пошаговом виде на вкладке «Участники».')
                : emptyCatalogMarkup('layout-grid', 'Выберите шаблон',
                    'Нажмите на шаблон сверху — появятся пустые ячейки групп.');
            refreshIcons();
            return;
        }
        const blocks = new Map((data.blocks || []).map((block) => [block.group.id, block]));
        host.innerHTML = data.groups.map((group, index) => {
            const capacity = Number(data.group_capacity?.[group.id]) || 0;
            const block = blocks.get(group.id);
            const title = format === 'league' ? 'Таблица' : `Группа ${group.name}`;
            return `
                <section class="board-group${block?.finished ? ' finished' : ''}">
                    <header>
                        <strong>${escapeHtml(title)}</strong>
                        ${block?.finished ? '<span class="board-badge">доиграна</span>' : ''}
                    </header>
                    ${locked && block?.matches.length ? '' : `
                        <div class="board-cells">${groupCellsMarkup(group, index, entries, capacity, locked)}</div>`}
                    ${matrixMarkup(group, block, entries)}
                </section>`;
        }).join('');
        host.classList.toggle('reveal', board.reveal);
        board.reveal = false;
        refreshIcons();
    }

    /* --- Сетка плей-офф --- */

    function bracketMatchMarkup(match, number) {
        if (match.is_bye) {
            const team = match.home.is_bye ? match.away : match.home;
            return `
                <div class="bk-match bye">
                    <div class="bk-row${team.entry_id ? '' : ' pending'}"><span class="bk-team">${team.entry_id ? logoMarkup(team.team_name, team.team_logo_url) : ''}<span class="bk-name">${escapeHtml(team.team_name)}</span></span></div>
                    <div class="bk-row pending"><span>проходит без игры</span></div>
                </div>`;
        }
        const ready = Boolean(match.home.entry_id && match.away.entry_id);
        const row = (side, score, pen) => {
            const team = match[side];
            const win = match.winner_entry_id && match.winner_entry_id === team.entry_id;
            return `
                <div class="bk-row${team.entry_id ? '' : ' pending'}${win ? ' win' : ''}">
                    <span class="bk-team">${team.entry_id ? logoMarkup(team.team_name, team.team_logo_url) : ''}<span class="bk-name">${escapeHtml(team.team_name)}</span></span>
                    <span class="bk-score">${score === null ? '' : score}${pen !== null && pen !== undefined
                        && match.home_score === match.away_score && score !== null ? `<small>(${pen})</small>` : ''}</span>
                </div>`;
        };
        return `
            <button type="button" class="bk-match${match.is_played ? ' played' : ''}${ready ? ' ready' : ''}"
                data-board-match="${match.id}" ${ready ? '' : 'disabled'}>
                <span class="bk-no">${number}${match.kickoff_at ? ` · ${escapeHtml(formatKickoff(match.kickoff_at))}` : ''}</span>
                ${row('home', match.home_score, match.home_penalty)}
                ${row('away', match.away_score, match.away_penalty)}
            </button>`;
    }

    function renderBracket(data) {
        const wrap = byId('boardBracketWrap');
        const matches = data.playoff || [];
        const placement = data.placement || [];
        wrap.hidden = !matches.length && !placement.length;
        // Кнопка «Добавить матчи за места» показывается вместе с сеткой.
        const canAddPlacement = data.settings.format === 'groups_playoff' && data.groups.length
            && data.built && !placement.length;
        // Матчи за места — тоже деревом: полуфиналы за 5–8 → «За 5 место» и «За 7 место».
        const placementRounds = [...new Set(placement.map((match) => match.round_no))].sort((a, b) => a - b);
        byId('boardPlacement').innerHTML = placement.length ? `
            <h3 class="board-title">Матчи за места</h3>
            <div class="board-bracket placement-bracket">${placementRounds.map((round, index) => `
                <div class="bk-round" style="--depth:${index}">
                    <p class="bk-round-title">${index === 0 && placementRounds.length > 1 ? 'Полуфиналы' : 'Матчи за места'}</p>
                    <div class="bk-round-body">${placement.filter((match) => match.round_no === round).map((match) => `
                        <div class="bk-slot">${bracketMatchMarkup(match, match.label)}</div>`).join('')}</div>
                </div>`).join('')}</div>`
            : canAddPlacement ? `
            <div class="placement-offer">
                <span>Команды, не вышедшие из групп, могут доиграть за 5-е и следующие места.</span>
                <button type="button" class="btn-secondary" data-add-placement>Добавить матчи за места</button>
            </div>` : '';
        if (!matches.length) {
            byId('boardBracket').innerHTML = '';
            byId('boardResults').innerHTML = '';
            return;
        }
        const bronze = matches.find((match) => match.label === 'За 3 место');
        const main = matches.filter((match) => match !== bronze);
        const rounds = [];
        main.forEach((match) => {
            let round = rounds.find((item) => item.no === match.round_no);
            if (!round) {
                round = { no: match.round_no, label: match.label, matches: [] };
                rounds.push(round);
            }
            round.matches.push(match);
        });
        rounds.sort((a, b) => a.no - b.no);
        let counter = 0;
        const numbers = new Map();
        rounds.forEach((round) => round.matches.forEach((match) => {
            if (!match.is_bye) numbers.set(match.id, ++counter);
        }));
        if (bronze) numbers.set(bronze.id, ++counter);

        byId('boardBracket').innerHTML = rounds.map((round, index) => `
            <div class="bk-round" style="--depth:${index}">
                <p class="bk-round-title">${escapeHtml(round.label || 'Раунд')}</p>
                <div class="bk-round-body">
                    ${round.matches.map((match) => `<div class="bk-slot">${bracketMatchMarkup(match, numbers.get(match.id) || '')}</div>`).join('')}
                </div>
                ${index === rounds.length - 1 && bronze ? `
                    <div class="bk-bronze">
                        <p class="bk-round-title">За 3 место</p>
                        ${bracketMatchMarkup(bronze, numbers.get(bronze.id))}
                    </div>` : ''}
            </div>`).join('');

        const results = data.results || [];
        byId('boardResults').innerHTML = results.length ? results.map((row) => `
            <span class="board-medal m${row.place}"><b>${row.place}</b>${logoMarkup(row.team_name, row.team_logo_url)}${escapeHtml(row.team_name)}</span>`).join('') : '';
    }

    /* --- Ввод счёта прямо на полотне --- */

    function findMatch(id) {
        const data = categoryOverview();
        if (!data) return null;
        const all = (data.blocks || []).flatMap((block) => block.matches)
            .concat(data.playoff || [], data.placement || []);
        return all.find((match) => Number(match.id) === Number(id)) || null;
    }

    function openPopover(matchId, anchor) {
        const match = findMatch(matchId);
        if (!match || match.is_bye || !match.home.entry_id || !match.away.entry_id) return;
        board.popoverMatch = match;
        const pop = byId('scorePopover');
        const playoff = match.stage === 'playoff';
        const value = (number) => (number === null || number === undefined ? '' : number);
        pop.innerHTML = `
            <p class="sp-title">${escapeHtml(match.label || (match.group_name ? `Группа ${match.group_name} · тур ${match.round_no}` : 'Матч'))}</p>
            <div class="sp-row">
                <span class="sp-team">${escapeHtml(match.home.team_name)}</span>
                <input type="number" min="0" max="99" inputmode="numeric" data-sp="home" value="${value(match.home_score)}" aria-label="Голы ${escapeHtml(match.home.team_name)}">
                <em>:</em>
                <input type="number" min="0" max="99" inputmode="numeric" data-sp="away" value="${value(match.away_score)}" aria-label="Голы ${escapeHtml(match.away.team_name)}">
                <span class="sp-team">${escapeHtml(match.away.team_name)}</span>
            </div>
            ${playoff ? `
                <div class="sp-row sp-pen" hidden>
                    <span class="sp-team">пенальти</span>
                    <input type="number" min="0" max="99" inputmode="numeric" data-sp="hpen" value="${value(match.home_penalty)}" aria-label="Пенальти хозяев">
                    <em>:</em>
                    <input type="number" min="0" max="99" inputmode="numeric" data-sp="apen" value="${value(match.away_penalty)}" aria-label="Пенальти гостей">
                    <span class="sp-team"></span>
                </div>` : ''}
            <div class="sp-when">
                <input type="datetime-local" data-sp="kickoff" value="${escapeHtml(match.kickoff_at || '')}" aria-label="Дата и время матча">
                <select data-sp="stadium" aria-label="Стадион">
                    <option value="">Стадион не выбран</option>
                    ${(categoryOverview()?.stadiums || []).map((stadium) => `<option value="${stadium.id}"
                        ${match.stadium_id === stadium.id ? 'selected' : ''}>${escapeHtml(stadium.name)}</option>`).join('')}
                </select>
            </div>
            <div class="sp-goals" data-sp-goals><p class="sp-hint">Загружаем состав…</p></div>
            <p class="sp-error" hidden></p>
            <div class="sp-actions">
                ${match.is_played ? '<button type="button" class="sp-link" data-sp-action="protocol">Протокол</button>' : ''}
                ${match.is_played ? '<button type="button" class="sp-link" data-sp-action="clear">Очистить</button>' : ''}
                <button type="button" class="sp-save" data-sp-action="save">Сохранить</button>
            </div>`;
        pop.hidden = false;
        syncPenalty();
        board.anchor = anchor;
        placePopover();
        // Без прокрутки: иначе окно турнира прокрутится и окошко тут же закроется.
        pop.querySelector('[data-sp="home"]').focus({ preventScroll: true });
        pop.querySelector('[data-sp="home"]').select();
        board.popoverOpenedAt = Date.now();
        loadGoalProtocol(match.id);
    }

    function placePopover() {
        const pop = byId('scorePopover');
        const anchor = board.anchor;
        if (!anchor || pop.hidden) return;
        const rect = anchor.getBoundingClientRect();
        const width = pop.offsetWidth;
        const height = pop.offsetHeight;
        const left = Math.min(Math.max(12, rect.left + rect.width / 2 - width / 2), window.innerWidth - width - 12);
        const below = rect.bottom + 8 + height < window.innerHeight;
        const top = below ? rect.bottom + 8 : Math.max(12, rect.top - height - 8);
        pop.style.left = `${left}px`;
        pop.style.top = `${Math.max(12, Math.min(top, window.innerHeight - height - 12))}px`;
    }

    /* Кто забил и на какой минуте. Пишется в протокол матча — оттуда считаются бомбардиры.
       Составы и карточки, внесённые в полном протоколе, сохраняются как были. */

    async function loadGoalProtocol(matchId) {
        board.protocol = null;
        board.goals = { home: [], away: [] };
        try {
            const data = await apiJson(`/api/tournament-matches/${matchId}/protocol`);
            if (!board.popoverMatch || board.popoverMatch.id !== matchId) return;
            board.protocol = data.protocol;
            const homeId = data.protocol.home?.entry_id;
            (data.protocol.events || []).filter((event) => event.kind === 'goal').forEach((event) => {
                const side = event.entry_id === homeId ? 'home' : 'away';
                board.goals[side].push({
                    member_id: event.is_own_goal ? 'og' : (event.member_id || ''),
                    minute: event.minute ?? '',
                    is_penalty: Boolean(event.is_penalty),
                    assist_member_id: event.assist_member_id || null,
                    own_member_id: event.is_own_goal ? event.member_id : null,
                });
            });
        } catch (error) {
            board.protocol = null;
        }
        renderGoals();
    }

    function readGoalsFromDom() {
        const pop = byId('scorePopover');
        pop.querySelectorAll('[data-goal-side]').forEach((row) => {
            const goal = board.goals[row.dataset.goalSide]?.[Number(row.dataset.goalIndex)];
            if (!goal) return;
            goal.member_id = row.querySelector('select').value;
            goal.minute = row.querySelector('input').value;
        });
    }

    function renderGoals() {
        const pop = byId('scorePopover');
        const host = pop.querySelector('[data-sp-goals]');
        const match = board.popoverMatch;
        if (!host || !match) return;
        if (!board.protocol) {
            host.innerHTML = '';
            placePopover();
            return;
        }
        readGoalsFromDom();
        const score = (key) => {
            const value = pop.querySelector(`[data-sp="${key}"]`).value.trim();
            return value === '' ? 0 : Math.max(0, Math.min(30, Number(value) || 0));
        };
        const counts = { home: score('home'), away: score('away') };
        ['home', 'away'].forEach((side) => {
            const list = board.goals[side];
            while (list.length < counts[side]) list.push({ member_id: '', minute: '', is_penalty: false });
            list.length = counts[side];
        });
        if (!counts.home && !counts.away) {
            host.innerHTML = '';
            placePopover();
            return;
        }
        const option = (player, selected) => `<option value="${player.id}" ${String(selected) === String(player.id) ? 'selected' : ''}>
            ${escapeHtml([player.number ? `№${player.number}` : '', player.short_name || player.name].filter(Boolean).join(' '))}</option>`;
        const sideBlock = (side) => {
            const block = board.protocol[side];
            const squad = block?.squad || [];
            if (!counts[side]) return '';
            return `
                <div class="sp-goal-side">
                    <p class="sp-goal-team">${logoMarkup(match[side].team_name, match[side].team_logo_url)}
                        ${escapeHtml(match[side].team_name)}</p>
                    ${board.goals[side].map((goal, index) => `
                        <div class="sp-goal" data-goal-side="${side}" data-goal-index="${index}">
                            <span class="sp-goal-ball">⚽</span>
                            <select aria-label="Кто забил">
                                <option value="">— кто забил —</option>
                                ${squad.map((player) => option(player, goal.member_id)).join('')}
                                <option value="og" ${goal.member_id === 'og' ? 'selected' : ''}>Автогол соперника</option>
                            </select>
                            <input type="number" min="0" max="200" inputmode="numeric" placeholder="мин"
                                value="${escapeHtml(String(goal.minute ?? ''))}" aria-label="Минута">
                            <span class="sp-goal-min">′</span>
                        </div>`).join('')}
                    ${squad.length ? '' : '<p class="sp-hint">В составе команды нет игроков — добавьте их в карточке команды.</p>'}
                </div>`;
        };
        host.innerHTML = `<p class="sp-goals-title">Голы <small>необязательно</small></p>${sideBlock('home')}${sideBlock('away')}`;
        placePopover();
    }

    async function saveGoals(clear) {
        const match = board.popoverMatch;
        const protocol = board.protocol;
        if (!match || !protocol) return;
        readGoalsFromDom();
        const hadGoals = (protocol.events || []).some((event) => event.kind === 'goal');
        const goals = clear ? { home: [], away: [] } : board.goals;
        const any = goals.home.length || goals.away.length;
        if (!any && !hadGoals) return;
        const events = [];
        ['home', 'away'].forEach((side) => {
            goals[side].forEach((goal) => {
                const own = goal.member_id === 'og';
                events.push({
                    side,
                    kind: 'goal',
                    member_id: own ? (goal.own_member_id || null) : (goal.member_id ? Number(goal.member_id) : null),
                    minute: goal.minute === '' ? null : Number(goal.minute),
                    is_own_goal: own,
                    is_penalty: Boolean(goal.is_penalty),
                    assist_member_id: own ? null : goal.assist_member_id,
                });
            });
        });
        // Карточки и составы из полного протокола не теряем.
        const homeId = protocol.home?.entry_id;
        (protocol.events || []).filter((event) => event.kind === 'card').forEach((event) => {
            events.push({
                side: event.entry_id === homeId ? 'home' : 'away',
                kind: 'card',
                member_id: event.member_id,
                minute: event.minute,
                card: event.card,
            });
        });
        const lineups = {};
        ['home', 'away'].forEach((side) => {
            lineups[side] = (protocol[side]?.lineup || []).map((row) => ({
                member_id: row.member_id,
                is_starting: row.is_starting,
                is_goalkeeper: row.is_goalkeeper,
                minutes: row.minutes,
            }));
        });
        await apiJson(`/api/tournament-matches/${match.id}/protocol`, {
            method: 'PUT',
            body: JSON.stringify({ lineups, events }),
        });
    }

    function syncPenalty() {
        const pop = byId('scorePopover');
        const pen = pop.querySelector('.sp-pen');
        if (!pen) return;
        const home = pop.querySelector('[data-sp="home"]').value;
        const away = pop.querySelector('[data-sp="away"]').value;
        pen.hidden = !(home !== '' && home === away);
    }

    function closePopover() {
        const pop = byId('scorePopover');
        if (pop) pop.hidden = true;
        board.popoverMatch = null;
    }

    async function savePopover(clear = false) {
        const match = board.popoverMatch;
        if (!match) return;
        const pop = byId('scorePopover');
        const read = (key) => {
            const input = pop.querySelector(`[data-sp="${key}"]`);
            return input && input.value.trim() !== '' && !clear ? Number(input.value) : null;
        };
        const payload = { home_score: read('home'), away_score: read('away') };
        // Время и стадион матча правятся здесь же (раньше — в строках матчей).
        payload.kickoff_at = pop.querySelector('[data-sp="kickoff"]').value;
        payload.stadium_id = pop.querySelector('[data-sp="stadium"]').value || null;
        if (match.stage === 'playoff') {
            payload.home_penalty = read('hpen');
            payload.away_penalty = read('apen');
        }
        const error = pop.querySelector('.sp-error');
        if (!clear && (payload.home_score === null) !== (payload.away_score === null)) {
            error.hidden = false;
            error.textContent = 'Укажите голы обеих команд';
            return;
        }
        try {
            const result = await apiJson(`/api/tournament-matches/${match.id}`, {
                method: 'PUT',
                body: JSON.stringify(payload),
            });
            let warning = result.warning;
            // Сначала счёт, потом голы: протокол обязан сходиться с уже сохранённым счётом.
            if (clear) {
                await saveGoals(true);
            } else {
                try {
                    await saveGoals(false);
                    warning = null;
                } catch (goalError) {
                    warning = `Счёт сохранён, но голы не записаны: ${goalError.message}`;
                }
            }
            closePopover();
            await loadCategory();
            if (warning) showFormError('boardError', warning);
        } catch (requestError) {
            error.hidden = false;
            error.textContent = requestError.message;
        }
    }

    /* --- Действия полотна --- */

    async function placeEntry(entryId, cell) {
        const index = cell.dataset.groupIndex;
        try {
            showFormError('boardError');
            const result = await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}/place`, {
                method: 'POST',
                body: JSON.stringify({
                    age_group: catalogState.age,
                    entry_id: Number(entryId),
                    group_index: index === '' || index === undefined ? null : Number(index),
                    slot: cell.dataset.slot ? Number(cell.dataset.slot) : null,
                }),
            });
            await loadCategory();
            if (result.calendar_reset) {
                showFormError('boardError', 'Календарь сброшен: не все команды на местах. '
                    + 'Расставьте их и нажмите «Составить календарь».');
            }
        } catch (error) {
            showFormError('boardError', error.message);
        }
    }

    async function togglePlacement(enabled) {
        const data = categoryOverview();
        if (!data) return;
        try {
            showFormError('boardError');
            if (data.groups.length) {
                // Группы уже есть — добавляем или убираем только матчи за места, турнир не пересобираем.
                await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}/placement`, {
                    method: 'POST',
                    body: JSON.stringify({ age_group: catalogState.age, enabled }),
                });
            } else {
                await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}/format`, {
                    method: 'PUT',
                    body: JSON.stringify({ age_group: catalogState.age, settings: { ...data.settings, placement: enabled } }),
                });
            }
            await loadCategory();
        } catch (error) {
            showFormError('boardError', error.message);
            await loadCategory();
        }
    }

    async function build(draw) {
        const data = categoryOverview();
        if (data?.built && !window.confirm(draw
            ? 'Ячейки заполнятся по новому жребию, календарь составится заново. Продолжить?'
            : 'Календарь составится заново по текущим ячейкам. Продолжить?')) return;
        try {
            showFormError('boardError');
            await apiJson(`/api/tournaments/${catalogState.entriesTournamentId}/build`, {
                method: 'POST',
                body: JSON.stringify({ age_group: catalogState.age, draw }),
            });
            board.reveal = draw;
            await loadCategory();
        } catch (error) {
            showFormError('boardError', error.message);
        }
    }

    function renderTemplates(data) {
        const host = byId('boardTemplates');
        const count = data?.counts?.confirmed || 0;
        const list = templatesFor(count, data?.settings?.placement !== false);
        const active = activeTemplateKey(data);
        const locked = Boolean(data?.has_results);
        host.innerHTML = list.length ? list.map((template) => `
            <button type="button" role="radio" aria-checked="${template.key === active}"
                class="board-template${template.key === active ? ' active' : ''}" data-template-key="${template.key}"
                ${locked && template.key !== active ? 'disabled' : ''}>
                <img class="board-template-art" src="${templateArt(template.key)}" alt="" loading="lazy">
                <strong>${escapeHtml(template.title)}</strong>
                <small>${escapeHtml(template.sub)}</small>
            </button>`).join('') : '<span class="board-empty">Нужно минимум 2 подтверждённые команды</span>';
        board.templates = list;
    }

    function renderBoard() {
        const data = categoryOverview();
        if (!data) return;
        renderTemplates(data);
        const locked = Boolean(data.has_results);
        const knockout = data.settings.format === 'knockout';
        byId('boardDrawBtn').disabled = locked || (data.counts?.confirmed || 0) < 2;
        byId('boardBuildBtn').hidden = knockout || !data.groups.length;
        byId('boardBuildBtn').disabled = locked;
        byId('boardScheduleBtn').hidden = !data.built;
        byId('boardResetBtn').hidden = !data.built;
        const placementBox = byId('boardPlacementField');
        placementBox.hidden = data.settings.format !== 'groups_playoff';
        const placementInput = placementBox.querySelector('input');
        const placementPlayed = (data.placement || []).some((match) => match.is_played);
        // Галочка отражает, есть ли матчи за места на самом деле (в турнирах, собранных раньше, их нет).
        placementInput.checked = data.groups.length && data.built
            ? (data.placement || []).length > 0
            : data.settings.placement !== false;
        placementInput.disabled = placementPlayed;
        byId('boardDrawBtn').querySelector('span').textContent = data.built ? 'Новая жеребьёвка' : 'Жеребьёвка';
        renderGroupsBoard(data);
        renderBracket(data);
        refreshIcons();
    }

    function bind() {
        byId('boardTemplates').addEventListener('click', (event) => {
            const button = event.target.closest('[data-template-key]');
            if (!button || button.classList.contains('active')) return;
            const template = (board.templates || []).find((item) => item.key === button.dataset.templateKey);
            if (template) applyTemplate(template);
        });
        byId('boardDrawBtn').addEventListener('click', () => build(true));
        byId('boardPlacementField').addEventListener('change', (event) => togglePlacement(event.target.checked));
        byId('boardPlacement').addEventListener('click', (event) => {
            if (event.target.closest('[data-add-placement]')) togglePlacement(true);
        });
        byId('boardBuildBtn').addEventListener('click', () => build(false));
        byId('boardScheduleBtn').addEventListener('click', openScheduleDialog);
        byId('boardResetBtn').addEventListener('click', () => resetCategory().catch(showPageError));
        const panel = byId('boardPanel');
        bindDragBoard(panel, {
            item: '[data-board-entry]',
            zone: '[data-cell]',
            isLocked: () => Boolean(categoryOverview()?.has_results),
            onDrop: (el, cell) => placeEntry(el.dataset.boardEntry, cell),
        });
        panel.addEventListener('click', (event) => {
            const target = event.target.closest('[data-board-match]');
            if (target && !target.disabled) openPopover(target.dataset.boardMatch, target);
        });
        const pop = byId('scorePopover');
        pop.addEventListener('input', (event) => {
            syncPenalty();
            if (event.target.matches('[data-sp="home"], [data-sp="away"]')) renderGoals();
        });
        pop.addEventListener('click', (event) => {
            const action = event.target.closest('[data-sp-action]')?.dataset.spAction;
            if (action === 'save') savePopover();
            if (action === 'clear') savePopover(true);
            if (action === 'protocol') {
                const id = board.popoverMatch?.id;
                closePopover();
                if (id) openProtocol(id).catch(showPageError);
            }
        });
        pop.addEventListener('keydown', (event) => {
            if (event.key === 'Enter') { event.preventDefault(); savePopover(); }
            if (event.key === 'Escape') { event.stopPropagation(); closePopover(); }
        });
        document.addEventListener('pointerdown', (event) => {
            if (!pop.hidden && !event.target.closest('#scorePopover, [data-board-match]')) closePopover();
        });
        // Прокрутили окно — окошко счёта отрывается от матча, закрываем (но не сразу после открытия).
        byId('tournamentEntriesModal').addEventListener('scroll', () => {
            if (Date.now() - (board.popoverOpenedAt || 0) > 400) closePopover();
        }, true);
    }

    // Встраиваемся в общую перерисовку категории.
    const baseRenderCategory = renderCategory;
    renderCategory = function renderCategoryWithBoard() {
        baseRenderCategory();
        closePopover();
        renderBoard();
    };

    bind();
})();
