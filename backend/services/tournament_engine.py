"""Чистая логика турнира: без Flask и базы, чтобы её можно было проверить тестами.

Здесь живут правила, которые легко сломать мелкой правкой:
круговая система, таблица с дополнительными показателями, посев плей-офф
и расстановка матчей по времени.
"""
import itertools
import math
import random
from datetime import datetime, timedelta


# ===== ФОРМАТЫ КАТЕГОРИИ =====

FORMAT_GROUPS_PLAYOFF = 'groups_playoff'
FORMAT_LEAGUE = 'league'
FORMAT_KNOCKOUT = 'knockout'

FORMAT_TITLES = {
    FORMAT_GROUPS_PLAYOFF: 'Группы + плей-офф',
    FORMAT_LEAGUE: 'Круговой турнир',
    FORMAT_KNOCKOUT: 'Олимпийская система',
}

TIEBREAK_H2H = 'h2h'          # сначала личные встречи, потом общая разница
TIEBREAK_OVERALL = 'overall'  # сначала общая разница, личные встречи — в конце

DEFAULT_SETTINGS = {
    'format': FORMAT_GROUPS_PLAYOFF,
    'groups': 2,
    'advance': 2,
    'third_place': True,
    'legs': 1,
    'tiebreak': TIEBREAK_H2H,
    'win_points': 3,
    'draw_points': 1,
}

MAX_GROUPS = 16


def normalize_settings(raw):
    """Приводит настройки категории к допустимым значениям."""
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULT_SETTINGS)

    fmt = raw.get('format')
    if fmt in FORMAT_TITLES:
        out['format'] = fmt

    def number(key, low, high):
        try:
            value = int(raw.get(key, out[key]))
        except (TypeError, ValueError):
            return
        out[key] = max(low, min(high, value))

    number('groups', 1, MAX_GROUPS)
    number('advance', 1, 4)
    number('legs', 1, 2)
    number('win_points', 1, 5)
    number('draw_points', 0, 3)
    if 'third_place' in raw:
        out['third_place'] = bool(raw.get('third_place'))
    if raw.get('tiebreak') in (TIEBREAK_H2H, TIEBREAK_OVERALL):
        out['tiebreak'] = raw['tiebreak']

    if out['format'] == FORMAT_LEAGUE:
        out['groups'] = 1
    return out


def split_sizes(total, groups):
    """Как разложить total команд по groups группам максимально ровно."""
    if groups <= 0:
        return []
    base, extra = divmod(total, groups)
    return [base + (1 if index < extra else 0) for index in range(groups)]


def round_robin_match_count(size, legs=1):
    return size * (size - 1) // 2 * legs


def next_power_of_two(value):
    size = 1
    while size < value:
        size *= 2
    return size


def knockout_round_name(matches_in_round):
    names = {1: 'Финал', 2: 'Полуфинал', 4: '1/4 финала', 8: '1/8 финала', 16: '1/16 финала'}
    return names.get(matches_in_round, f'1/{matches_in_round} финала')


def describe_plan(team_count, settings):
    """Человеческое описание схемы: сколько групп, кто выходит, сколько матчей.

    Возвращает список шагов и общее число матчей — организатор видит, во что
    превратится турнир, до того как нажмёт кнопку.
    """
    s = normalize_settings(settings)
    steps = []
    warnings = []
    group_matches = 0
    playoff_matches = 0

    if team_count < 2:
        return {'steps': [], 'warnings': ['Нужно минимум 2 подтверждённые команды'],
                'group_matches': 0, 'playoff_matches': 0, 'total_matches': 0}

    qualified = 0
    if s['format'] == FORMAT_LEAGUE:
        group_matches = round_robin_match_count(team_count, s['legs'])
        legs = 'в два круга (дома и в гостях)' if s['legs'] == 2 else 'в один круг'
        steps.append(f'{team_count} команд играют каждый с каждым {legs}')
        steps.append('Победитель — первое место в таблице')
    elif s['format'] == FORMAT_GROUPS_PLAYOFF:
        groups = min(s['groups'], team_count // 2) or 1
        if groups != s['groups']:
            warnings.append(f'Для {team_count} команд групп может быть не больше {groups}')
        sizes = split_sizes(team_count, groups)
        group_matches = sum(round_robin_match_count(size, s['legs']) for size in sizes)
        word = 'команды' if 2 <= max(sizes) % 10 <= 4 and not 12 <= max(sizes) % 100 <= 14 else 'команд'
        span = str(sizes[0]) if len(set(sizes)) == 1 else f'{min(sizes)}–{max(sizes)}'
        steps.append(f'{groups} гр. по {span} {word} — каждый с каждым')
        advance = min(s['advance'], min(sizes) - 1) if min(sizes) > 1 else 1
        if advance != s['advance']:
            warnings.append(f'Из группы на {min(sizes)} команды выходят не больше {advance}')
        qualified = groups * advance
        steps.append(f'Из каждой группы выходят {advance} → {qualified} команд в плей-офф')
    else:
        qualified = team_count
        steps.append(f'{team_count} команд по жребию, проигравший выбывает')

    if s['format'] != FORMAT_LEAGUE and qualified >= 2:
        size = next_power_of_two(qualified)
        byes = size - qualified
        first = knockout_round_name(size // 2)
        line = f'Плей-офф начинается с этапа «{first}»'
        if byes:
            line += f', {byes} команд(ы) проходят дальше без игры'
        steps.append(line)
        playoff_matches = qualified - 1
        if s['third_place'] and qualified >= 4:
            playoff_matches += 1
            steps.append('Финал и матч за 3 место')
        else:
            steps.append('Финал определяет победителя')

    return {
        'steps': steps,
        'warnings': warnings,
        'group_matches': group_matches,
        'playoff_matches': playoff_matches,
        'total_matches': group_matches + playoff_matches,
    }


# ===== КРУГОВАЯ СИСТЕМА =====

def round_robin_rounds(items, legs=1):
    """Каждый с каждым: «круговой» метод Бергера.

    Один участник стоит на месте, остальные сдвигаются по кругу. При нечётном
    числе добавляем «пустого» — его соперник в этом туре отдыхает.
    Хозяева чередуются, чтобы ни одна команда не стояла хозяином всё время.
    Во втором круге пары те же, но хозяева меняются местами.
    """
    players = list(items)
    if len(players) < 2:
        return []
    if len(players) % 2:
        players.append(None)

    count = len(players)
    half = count // 2
    rounds = []
    for round_index in range(count - 1):
        pairs = []
        for index in range(half):
            home, away = players[index], players[count - 1 - index]
            if home is None or away is None:
                continue
            # У зафиксированного участника хозяин меняется каждый тур,
            # у остальных — в зависимости от позиции, как в таблицах Бергера.
            if index == 0:
                swap = round_index % 2 == 1
            else:
                swap = index % 2 == 1
            pairs.append((away, home) if swap else (home, away))
        rounds.append(pairs)
        players = [players[0]] + [players[-1]] + players[1:-1]

    if legs == 2:
        rounds += [[(away, home) for home, away in pairs] for pairs in rounds[:]]
    return rounds


# ===== ТУРНИРНАЯ ТАБЛИЦА =====

def _blank_row(team):
    return {
        **team,
        'played': 0, 'won': 0, 'drawn': 0, 'lost': 0,
        'goals_for': 0, 'goals_against': 0, 'diff': 0, 'points': 0,
        'form': [],
    }


def _accumulate(rows, results, win_points, draw_points, with_form=False):
    for home_id, away_id, home_goals, away_goals in results:
        if home_id not in rows or away_id not in rows:
            continue
        home, away = rows[home_id], rows[away_id]
        home['played'] += 1
        away['played'] += 1
        home['goals_for'] += home_goals
        home['goals_against'] += away_goals
        away['goals_for'] += away_goals
        away['goals_against'] += home_goals
        if home_goals > away_goals:
            home['won'] += 1
            away['lost'] += 1
            home['points'] += win_points
            outcome = ('W', 'L')
        elif home_goals < away_goals:
            away['won'] += 1
            home['lost'] += 1
            away['points'] += win_points
            outcome = ('L', 'W')
        else:
            home['drawn'] += 1
            away['drawn'] += 1
            home['points'] += draw_points
            away['points'] += draw_points
            outcome = ('D', 'D')
        if with_form:
            home['form'].append(outcome[0])
            away['form'].append(outcome[1])
    for row in rows.values():
        row['diff'] = row['goals_for'] - row['goals_against']


def _mini_table(ids, results, win_points, draw_points):
    """Таблица только из матчей между командами ids."""
    rows = {team_id: _blank_row({'id': team_id}) for team_id in ids}
    inner = [r for r in results if r[0] in rows and r[1] in rows]
    _accumulate(rows, inner, win_points, draw_points)
    return rows


def _split_by(ids, key):
    """Разбивает список на блоки с одинаковым значением key, по убыванию."""
    ordered = sorted(ids, key=key, reverse=True)
    return [list(block) for _, block in itertools.groupby(ordered, key=key)]


def _resolve_h2h(ids, results, win_points, draw_points, overall, depth=0):
    """Личные встречи по правилу УЕФА: если мини-таблица разделила
    равных лишь частично, оставшихся сравниваем заново между собой."""
    if len(ids) < 2 or depth > 6:
        return [ids]
    mini = _mini_table(ids, results, win_points, draw_points)
    key = lambda team_id: (mini[team_id]['points'], mini[team_id]['diff'], mini[team_id]['goals_for'])
    blocks = _split_by(ids, key)
    if len(blocks) == 1:
        return [ids]
    out = []
    for block in blocks:
        if len(block) > 1 and len(block) < len(ids):
            out.extend(_resolve_h2h(block, results, win_points, draw_points, overall, depth + 1))
        else:
            out.append(block)
    return out


def build_table(teams, results, tiebreak=TIEBREAK_H2H, win_points=3, draw_points=1):
    """Турнирная таблица.

    teams   — список словарей с ключом 'id' (+ любые поля для показа, 'team_name' обязательно);
    results — сыгранные матчи: (home_id, away_id, home_goals, away_goals) в порядке игры.

    Порядок при равенстве очков:
      h2h:     личные встречи (очки, разница, голы) → общая разница → забитые → победы
      overall: общая разница → забитые → победы → личные встречи
    Если и это не помогло — по алфавиту (на практике организатор бросает жребий).
    """
    rows = {team['id']: _blank_row(team) for team in teams}
    _accumulate(rows, results, win_points, draw_points, with_form=True)

    def overall_key(team_id):
        row = rows[team_id]
        return (row['diff'], row['goals_for'], row['won'])

    def name_key(team_id):
        return (rows[team_id].get('team_name') or '').lower()

    ordered = []
    for block in _split_by(list(rows), lambda team_id: rows[team_id]['points']):
        if len(block) == 1:
            ordered.extend(block)
            continue
        if tiebreak == TIEBREAK_H2H:
            for sub in _resolve_h2h(block, results, win_points, draw_points, rows):
                for tier in _split_by(sub, overall_key):
                    ordered.extend(sorted(tier, key=name_key))
        else:
            for tier in _split_by(block, overall_key):
                if len(tier) == 1:
                    ordered.extend(tier)
                    continue
                for sub in _resolve_h2h(tier, results, win_points, draw_points, rows):
                    ordered.extend(sorted(sub, key=name_key))

    table = []
    for place, team_id in enumerate(ordered, start=1):
        row = rows[team_id]
        row['place'] = place
        row['form'] = row['form'][-5:]
        table.append(row)
    return table


# ===== ПОСЕВ ПЛЕЙ-ОФФ =====

def bracket_positions(size):
    """Стандартная расстановка посева: при 8 — [1, 8, 4, 5, 2, 7, 3, 6].

    Сильнейшие сеяные оказываются в разных половинах и могут встретиться
    только в финале, а свободные места (bye) достаются первым номерам.
    """
    order = [1]
    while len(order) < size:
        total = len(order) * 2 + 1
        order = [seed for item in order for seed in (item, total - item)]
    return order


def _meet_round(slot_a, slot_b, size):
    """В каком раунде встретятся позиции сетки, если обе будут побеждать."""
    rounds = int(math.log2(size))
    for round_no in range(1, rounds + 1):
        block = 2 ** round_no
        if slot_a // block == slot_b // block:
            return round_no
    return rounds


def seed_group_qualifiers(group_names, advance, attempts=400, rng=None):
    """Посев вышедших из групп: возвращает список длиной в размер сетки.

    Элемент — (group_name, place) или None для свободного места (bye).
    Правила: победители групп сеются выше вторых мест и получают bye;
    команды одной группы не встречаются в первом раунде и разводятся
    как можно дальше (в идеале — только в финале).
    """
    rng = rng or random.Random(20260101)
    qualified = len(group_names) * advance
    size = next_power_of_two(max(qualified, 2))
    positions = bracket_positions(size)
    slot_of_seed = {seed: index for index, seed in enumerate(positions)}

    tiers = [[(name, place) for name in group_names] for place in range(1, advance + 1)]
    # Вторые места идут в обратном порядке групп — классика «1A–2B, 1B–2A».
    for index in range(1, len(tiers)):
        if index % 2 == 1:
            tiers[index] = list(reversed(tiers[index]))

    def cost(order):
        slots = {}
        for seed_no, item in enumerate(order, start=1):
            slots[item] = slot_of_seed[seed_no]
        total = 0
        rounds = int(math.log2(size))
        by_group = {}
        for (group, place), slot in slots.items():
            by_group.setdefault(group, []).append(slot)
        for group_slots in by_group.values():
            for a, b in itertools.combinations(group_slots, 2):
                meet = _meet_round(a, b, size)
                # Чем раньше встреча одногруппников, тем хуже: первый раунд — почти запрет.
                total += 10 ** (rounds - meet + 1)
        return total

    best = [item for tier in tiers for item in tier]
    best_cost = cost(best)
    for _ in range(attempts):
        if best_cost == 0:
            break
        candidate = []
        for tier in tiers:
            shuffled = tier[:]
            rng.shuffle(shuffled)
            candidate.extend(shuffled)
        value = cost(candidate)
        if value < best_cost:
            best, best_cost = candidate, value

    seeds = best + [None] * (size - qualified)
    bracket = [None] * size
    for seed_no, item in enumerate(seeds, start=1):
        bracket[slot_of_seed[seed_no]] = item
    return bracket


def seed_knockout(items, rng=None):
    """Олимпийская система без групп: жребий, bye — первым по жребию."""
    rng = rng or random.Random()
    items = list(items)
    rng.shuffle(items)
    size = next_power_of_two(max(len(items), 2))
    positions = bracket_positions(size)
    seeds = items + [None] * (size - len(items))
    bracket = [None] * size
    for seed_no, item in enumerate(seeds, start=1):
        bracket[positions.index(seed_no)] = item
    return bracket


# ===== РАССТАНОВКА ПО ВРЕМЕНИ =====

class ScheduleItem:
    """Матч для расстановки.

    teams      — множество id команд (пустое, если участники ещё неизвестны);
    after      — ключи других матчей, которые должны закончиться раньше;
    not_before — не раньше этого момента (например, конец уже стоящего матча);
    key        — уникальный ключ матча.
    """

    def __init__(self, key, teams, after=(), not_before=None):
        self.key = key
        self.teams = set(teams)
        self.after = set(after)
        self.not_before = not_before


def schedule_matches(items, *, start_date, day_start, day_end, duration, gap, pitches,
                     fixed=(), max_days=120, prefer_rest=True):
    """Ставит матчи в сетку слотов: duration + gap, pitches полей параллельно.

    fixed — уже стоящие матчи, которые нельзя двигать: (start, teams).
    Правила:
      * на одном слоте не больше pitches матчей (с учётом fixed);
      * команда не играет два матча одновременно и не раньше конца прошлого;
      * матч не раньше, чем закончатся все матчи из его after;
      * по возможности у команды есть перерыв хотя бы в один слот.
    Возвращает словарь key -> datetime. Бросает ValueError, если не уместилось.
    """
    step = timedelta(minutes=duration + gap)
    length = timedelta(minutes=duration)

    def day_slots(day):
        slot = datetime.combine(day, day_start)
        last = datetime.combine(day, day_end)
        while slot + length <= last:
            yield slot
            slot += step

    slots = []
    for offset in range(max_days):
        slots.extend(day_slots(start_date + timedelta(days=offset)))
    if not slots:
        raise ValueError('В выбранные часы не помещается ни одного матча')

    # Занятость слотов: учитываем пересечение по времени, а не только точное совпадение.
    load = [0] * len(slots)
    teams_at = [set() for _ in slots]
    team_last_end = {}

    def overlapping(start):
        end = start + length
        return [i for i, slot in enumerate(slots) if slot < end and start < slot + length]

    for start, teams in fixed:
        for index in overlapping(start):
            load[index] += 1
            teams_at[index] |= set(teams)
        for team in teams:
            team_last_end[team] = max(team_last_end.get(team, start + length), start + length)

    placed_end = {}
    result = {}
    by_key = {item.key: item for item in items}

    def earliest(item):
        bound = slots[0]
        if item.not_before and item.not_before > bound:
            bound = item.not_before
        for dep in item.after:
            if dep in placed_end:
                bound = max(bound, placed_end[dep])
            elif dep in by_key:
                # Зависимость ещё не поставлена — значит порядок нарушен.
                return None
        return bound

    for item in items:
        bound = earliest(item)
        if bound is None:
            raise ValueError('Порядок матчей нарушен')
        chosen = None
        fallback = None
        for index, slot in enumerate(slots):
            if slot < bound or load[index] >= pitches:
                continue
            if item.teams & teams_at[index]:
                continue
            if any(team_last_end.get(team, slot) > slot for team in item.teams):
                continue
            rested = not prefer_rest or index == 0 or not (item.teams & teams_at[index - 1]) \
                or slots[index - 1].date() != slot.date()
            if rested:
                chosen = index
                break
            if fallback is None:
                fallback = index
            # Ищем отдых не дальше пары слотов вперёд, иначе турнир растянется.
            if index - fallback >= 2:
                break
        if chosen is None:
            chosen = fallback
        if chosen is None:
            raise ValueError('Не хватило дней: увеличьте время игрового дня или число полей')
        slot = slots[chosen]
        load[chosen] += 1
        teams_at[chosen] |= item.teams
        for team in item.teams:
            team_last_end[team] = slot + length
        placed_end[item.key] = slot + length
        result[item.key] = slot
    return result
