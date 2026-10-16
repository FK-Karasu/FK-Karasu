/* Обучение по разделу «Турниры»: один урок, разбитый на главы.
 *
 * Тур подсвечивает поле или кнопку, затемняет остальное и объясняет, что с ним делать.
 * Нужные окна открывает сам и закрывает только те, что открыл он, — окна пользователя не трогает.
 * Зависит от функций tournaments.js (openModal, openTournamentEntries, …), подключается после него.
 */
(() => {
    const STORAGE_KEY = 'tournamentTourProgress.v1';

    /* --- Данные, от которых зависят главы --- */

    const firstTournamentId = () => catalogState.tournaments[0]?.id || null;
    const firstTeamId = () => catalogState.teams[0]?.id || null;
    const hasTournament = () => Boolean(firstTournamentId());
    const hasTeam = () => Boolean(firstTeamId());
    const firstEntryTeamId = () => (catalogState.entries || [])
        .find((entry) => entry.status !== 'declined')?.team_id || null;
    // Заявки грузятся при открытии турнира, поэтому до этого смотрим просто на наличие турнира.
    const hasEntry = () => hasTournament() && (byId('tournamentEntriesModal').hidden
        ? true : Boolean(firstEntryTeamId()));

    function playedMatchId() {
        const data = catalogState.overview;
        if (!data) return null;
        const group = (data.blocks || []).flatMap((block) => block.matches).find((m) => m.is_played);
        const playoff = (data.playoff || []).find((m) => m.is_played);
        return (group || playoff)?.id || null;
    }

    /* Как открыть каждое окно. Окно открывается, только если оно сейчас закрыто. */
    const OPENERS = {
        catalogFilterModal: () => openCatalogFilter('tournaments'),
        tournamentModal: () => { resetTournamentForm(); openModal('tournamentModal'); },
        stadiumModal: () => openStadiumCreator(),
        stadiumImportModal: () => {
            showFormError('stadiumImportError');
            byId('stadiumImportResult').hidden = true;
            openModal('stadiumImportModal');
        },
        teamModal: () => { resetTeamForm(); openModal('teamModal'); },
        teamDetailsModal: () => openTeamDetails(firstTeamId()),
        memberModal: () => { resetMemberForm(); openModal('memberModal'); },
        teamShareModal: () => openTeamShare(firstTeamId()),
        tournamentEntriesModal: () => openTournamentEntries(firstTournamentId()),
        scheduleModal: () => openScheduleDialog(),
        rosterModal: () => (firstEntryTeamId() ? openRoster(firstEntryTeamId()) : null),
        matchProtocolModal: () => openProtocol(playedMatchId()),
        postStudioModal: () => openStudio({ age_group: catalogState.age }),
    };

    const field = (selector) => () => {
        const element = document.querySelector(selector);
        return element ? (element.closest('label, .tournament-catalog-field, .studio-field') || element) : null;
    };

    /* --- Содержание урока --- */

    const WORKSPACE = ['tournamentEntriesModal'];

    const CHAPTERS = [
        {
            key: 'overview',
            title: 'Знакомство',
            icon: 'compass',
            steps: [
                {
                    title: 'Урок по турнирам',
                    text: 'За один урок вы научитесь всему: добавлять стадионы и команды, создавать турнир, '
                        + 'проводить жеребьёвку, вносить счёт, вести плей-офф и делать картинки для соцсетей.'
                        + '<br><br>Листайте кнопкой <b>«Далее»</b> или стрелками на клавиатуре. '
                        + 'Выйти можно в любой момент — клавишей Esc.',
                },
                {
                    target: '#tournamentCatalogTabs',
                    tab: 'tournaments',
                    title: 'Три раздела',
                    text: '<b>Турниры</b> — сами соревнования. <b>Команды</b> и <b>Стадионы</b> — справочники: '
                        + 'заполняете их один раз и потом выбираете в любом турнире.',
                    tip: 'Правильный порядок: стадионы → команды → турнир.',
                },
                {
                    target: '#catalogPanel-tournaments .catalog-list-tools',
                    tab: 'tournaments',
                    title: 'Поиск и фильтр',
                    text: 'Ищите турнир по названию. Кнопка «Фильтр» отбирает по локации и возрасту.',
                },
                {
                    target: '#tournamentList',
                    tab: 'tournaments',
                    title: 'Список турниров',
                    text: 'Нажмите на <b>название турнира</b> — откроется окно управления: участники, схема, матчи, '
                        + 'плей-офф. Кнопка <b>⋮</b> справа — редактировать или удалить турнир.',
                },
            ],
        },
        {
            key: 'stadium',
            title: 'Стадионы',
            icon: 'map-pinned',
            steps: [
                {
                    target: '#openStadiumModalBtn',
                    tab: 'stadiums',
                    title: 'Добавить стадион',
                    text: 'Стадион нужен, чтобы указать в турнире место проведения и закрепить поле за матчем.',
                },
                {
                    target: '#openStadiumImportBtn',
                    tab: 'stadiums',
                    title: 'Импорт из карты',
                    text: 'Можно не вводить вручную: импорт загрузит футбольные поля выбранного района '
                        + 'из OpenStreetMap вместе с координатами.',
                },
                {
                    target: field('#stadiumImportArea'),
                    modals: ['stadiumImportModal'],
                    title: 'Выберите район',
                    text: 'Выберите область или город и нажмите «Импортировать». Повторы не создаются.',
                },
                {
                    target: field('#stadiumName'),
                    modals: ['stadiumModal'],
                    title: 'Название стадиона',
                    text: 'Как его называют родители и тренеры — так его будет видно в афише.',
                },
                {
                    target: field('#stadiumOwnerPhone'),
                    modals: ['stadiumModal'],
                    title: 'Телефон владельца',
                    text: 'Чтобы быстро договориться об аренде. Наружу, на сайт, не выводится.',
                },
                {
                    target: field('#stadiumLength'),
                    modals: ['stadiumModal'],
                    title: 'Размер поля',
                    text: 'Длина и ширина в метрах — необязательно, но помогает тренерам подготовиться.',
                },
                {
                    target: field('#stadiumPhoto'),
                    modals: ['stadiumModal'],
                    title: 'Фото',
                    text: 'Фото стадиона показывается в карточке турнира на сайте.',
                },
                {
                    target: '#stadiumMap',
                    modals: ['stadiumModal'],
                    title: 'Точка на карте — обязательно',
                    text: 'Нажмите на карту там, где находится поле. Без точки стадион не сохранится: '
                        + 'по ней гости строят маршрут.',
                },
                {
                    target: '#stadiumForm button[type="submit"]',
                    modals: ['stadiumModal'],
                    title: 'Сохранить',
                    text: 'Готово — стадион появится в списке и в выборе локации турнира.',
                },
            ],
        },
        {
            key: 'team',
            title: 'Команды и составы',
            icon: 'shield',
            steps: [
                {
                    target: '#openTeamModalBtn',
                    tab: 'teams',
                    title: 'Добавить команду',
                    text: 'Команда — это клуб. Один раз добавили — и заявляете её в любой турнир и в любую '
                        + 'возрастную категорию.',
                },
                {
                    target: field('#teamName'),
                    modals: ['teamModal'],
                    title: 'Название',
                    text: 'Обязательное поле. Два клуба с одинаковым названием создать нельзя.',
                },
                {
                    target: field('#teamLogo'),
                    modals: ['teamModal'],
                    title: 'Логотип',
                    text: 'PNG, JPG или WEBP. Логотип попадёт в таблицы, сетку и картинки для соцсетей.',
                },
                {
                    target: field('#teamTrainerName'),
                    modals: ['teamModal'],
                    title: 'Тренер',
                    text: 'ФИО и фото тренера. Ниже — телефоны администрации и тренера: '
                        + 'по ним вы будете приглашать команду на турниры.',
                },
                {
                    target: field('#teamClubAddress'),
                    modals: ['teamModal'],
                    title: 'Адрес клуба',
                    text: 'Необязательно, для вашей справки.',
                },
                {
                    target: '#teamForm button[type="submit"]',
                    modals: ['teamModal'],
                    title: 'Сохранить команду',
                    text: 'После сохранения откройте команду, чтобы добавить игроков.',
                },
                {
                    target: '#teamList',
                    tab: 'teams',
                    title: 'Карточка команды',
                    text: 'Нажмите на <b>название команды</b> — откроется её состав. Через <b>⋮</b> можно '
                        + 'отправить тренеру ссылку, отредактировать или удалить команду.',
                },
                {
                    requires: hasTeam,
                    target: '#teamContactSummary',
                    modals: ['teamDetailsModal'],
                    title: 'Контакты',
                    text: 'Здесь всё, что вы указали о клубе: тренер, телефоны, адрес.',
                },
                {
                    requires: hasTeam,
                    target: '#openMemberModalBtn',
                    modals: ['teamDetailsModal'],
                    title: 'Добавить игрока',
                    text: 'Состав нужен для протоколов матчей: кто забил, кто стоял в воротах, '
                        + 'кто получил карточку.',
                },
                {
                    target: field('#memberLastName'),
                    modals: ['memberModal'],
                    title: 'Фамилия и имя',
                    text: 'Обязательные поля. Отчество — по желанию.',
                },
                {
                    target: field('#memberBirthDate'),
                    modals: ['memberModal'],
                    title: 'Дата рождения',
                    text: 'Формат <b>дд.мм.гггг</b>. Если в турнире категория «2015», '
                        + 'по году рождения видно, подходит ли игрок.',
                },
                {
                    target: field('#memberTeamNumber'),
                    modals: ['memberModal'],
                    title: 'Номер и позиция',
                    text: 'Номер на футболке и амплуа. Позиция «Вратарь» нужна для приза лучшему вратарю.',
                },
                {
                    target: '#memberForm button[type="submit"]',
                    modals: ['memberModal'],
                    title: 'Сохранить игрока',
                    text: 'Добавляйте игроков по одному — или поручите это тренеру (следующий шаг).',
                },
                {
                    requires: hasTeam,
                    target: field('#teamShareTournament'),
                    modals: ['teamShareModal'],
                    title: 'Ссылка для тренера',
                    text: 'Выберите турнир и создайте ссылку. Тренер откроет её с телефона и сам заполнит '
                        + 'состав — правки принимаются до начала турнира.',
                },
                {
                    requires: hasTeam,
                    target: '#createTeamShareLink',
                    modals: ['teamShareModal'],
                    title: 'Создать и отправить',
                    text: 'После создания ссылку можно скопировать и отправить в Telegram. '
                        + '«Закрыть доступ» отключает ссылку сразу.',
                },
            ],
        },
        {
            key: 'create',
            title: 'Создание турнира',
            icon: 'trophy',
            steps: [
                {
                    target: '#openTournamentModalBtn',
                    tab: 'tournaments',
                    title: 'Создать турнир',
                    text: 'Сначала создаётся карточка: название, даты, место и возрастные категории.',
                },
                {
                    target: '#tournamentPosterPreview',
                    modals: ['tournamentModal'],
                    title: 'Афиша',
                    text: 'Необязательно. Картинка показывается на сайте и служит фоном для публикаций.',
                },
                {
                    target: field('#tournamentName'),
                    modals: ['tournamentModal'],
                    title: 'Название',
                    text: 'Например, «CAM Cup 2026». Так турнир будет называться везде.',
                },
                {
                    target: field('#tournamentStartDate'),
                    modals: ['tournamentModal'],
                    title: 'Даты и время начала',
                    text: 'Дата начала, время первого матча и дата окончания. '
                        + 'До времени начала тренеры могут править состав по ссылке.',
                },
                {
                    target: field('#tournamentLocation'),
                    modals: ['tournamentModal'],
                    title: 'Место проведения',
                    text: 'Выберите стадион из справочника. Нет нужного — в конце списка есть '
                        + '«Добавить стадион».',
                },
                {
                    target: '#tournamentAgeGroupChips',
                    fallback: field('#tournamentAgeGroupYear'),
                    modals: ['tournamentModal'],
                    title: 'Возрастные категории',
                    text: 'Выберите год рождения в списке — он добавится чипом. Можно несколько: '
                        + 'каждая категория — отдельный мини-турнир со своими группами и сеткой.',
                    tip: 'Свою подпись вроде «U-12» впишите в поле рядом и нажмите «Добавить».',
                },
                {
                    target: field('#tournamentPublished'),
                    modals: ['tournamentModal'],
                    title: 'Показать на сайте',
                    text: 'С галочкой турнир виден в публичной афише. Снимите её, пока готовите черновик.',
                },
                {
                    target: '#tournamentForm button[type="submit"]',
                    modals: ['tournamentModal'],
                    title: 'Сохранить',
                    text: 'Турнир появится в списке. Нажмите на его название, чтобы перейти к управлению.',
                },
            ],
        },
        {
            key: 'manage',
            title: 'Управление турниром',
            icon: 'layout-grid',
            steps: [
                {
                    requires: () => !hasTournament(),
                    title: 'Сначала создайте турнир',
                    text: 'Управление открывается внутри турнира. Создайте первый турнир, '
                        + 'а потом снова нажмите «Обучение» — покажем всё на нём.',
                },
                {
                    requires: hasTournament,
                    target: '#entriesTournamentMeta',
                    modals: WORKSPACE,
                    title: 'Окно управления',
                    text: 'Здесь проходит весь турнир. Под названием — даты, время, место и виден ли турнир на сайте.',
                },
                {
                    requires: hasTournament,
                    target: '.category-switch-row',
                    modals: WORKSPACE,
                    optional: true,
                    title: 'Категория',
                    text: 'Если категорий несколько, переключайтесь здесь. У каждой — свои участники, '
                        + 'схема, матчи и сетка. Число — подтверждённые команды.',
                },
                {
                    requires: hasTournament,
                    target: '#entryTabs',
                    modals: WORKSPACE,
                    title: 'Пять шагов турнира',
                    text: 'Идите слева направо: <b>Участники → Схема → Матчи → Плей-офф → Награды</b>. '
                        + 'Готовый шаг — зелёная галочка, следующий — оранжевая точка.',
                },
                {
                    requires: hasTournament,
                    target: '#entryTeamPicker',
                    modals: WORKSPACE,
                    entryTab: 'entries',
                    title: 'Шаг 1. Заявите команды',
                    text: 'Начните вводить название и выберите команды из списка — можно сразу несколько.',
                },
                {
                    requires: hasTournament,
                    target: '#entryAgeChips',
                    optional: true,
                    modals: WORKSPACE,
                    entryTab: 'entries',
                    title: 'В какие категории',
                    text: 'Отметьте галочками все категории, где клуб играет, — например, 2010-2011 A, '
                        + '2010-2011 B и 2012-2013 A. Заявки создадутся одним нажатием.',
                },
                {
                    requires: hasTournament,
                    target: '#addEntryBtn',
                    modals: WORKSPACE,
                    entryTab: 'entries',
                    title: 'Заявить',
                    text: 'Команды попадут в список со статусом «Приглашена».',
                },
                {
                    requires: hasTournament,
                    target: '#entriesList .entry-status',
                    fallback: '#entriesList',
                    modals: WORKSPACE,
                    entryTab: 'entries',
                    title: 'Статус: «Подтвердила»',
                    text: 'Играют <b>только подтвердившие</b> команды. Когда клуб дал согласие — '
                        + 'поменяйте статус. Отказавшиеся в жеребьёвку не попадут.',
                },
                {
                    requires: hasTournament,
                    target: '#entriesList [data-roster-team]',
                    modals: WORKSPACE,
                    entryTab: 'entries',
                    optional: true,
                    title: 'Игроки заявки',
                    text: 'Сколько игроков клуба играет в этой категории. Оранжевое «+2 ?» — двоим нужно выбрать '
                        + 'категорию: нажмите и разложите (подробно — глава «Состав по категориям»).',
                },
                {
                    requires: hasTournament,
                    target: '#formatCards',
                    modals: WORKSPACE,
                    entryTab: 'scheme',
                    title: 'Шаг 2. Выберите схему',
                    text: '<b>Группы + плей-офф</b> — как чемпионат мира. <b>Круговой</b> — все со всеми, '
                        + 'чемпион по таблице. <b>Олимпийская</b> — сразу на вылет.',
                    tip: '3–6 команд — круговой. 7 и больше — группы + плей-офф. Мало времени — олимпийская.',
                },
                {
                    requires: hasTournament,
                    target: '#formatOptions',
                    modals: WORKSPACE,
                    entryTab: 'scheme',
                    title: 'Настройки схемы',
                    text: 'Сколько групп и сколько команд выходит из группы, матч за 3 место. '
                        + 'Редкие правила — круги и равенство очков — спрятаны в «Дополнительно».',
                },
                {
                    requires: hasTournament,
                    target: '#schemePlan',
                    modals: WORKSPACE,
                    entryTab: 'scheme',
                    title: 'Как пройдёт турнир',
                    text: 'Система сразу считает схему: сколько групп, кто выходит, с какого этапа плей-офф '
                        + 'и сколько всего матчей. Меняйте настройки — план обновится.',
                },
                {
                    requires: hasTournament,
                    target: '#buildDrawBtn',
                    modals: WORKSPACE,
                    entryTab: 'scheme',
                    title: 'Жеребьёвка и календарь',
                    text: 'Одна кнопка делает всё: распределяет команды по группам, составляет '
                        + 'расписание туров и пустую сетку плей-офф.',
                },
                {
                    requires: hasTournament,
                    target: '#groupBoardSection',
                    modals: WORKSPACE,
                    entryTab: 'scheme',
                    optional: true,
                    title: 'Составы групп',
                    text: 'Не нравится жребий — перетащите команду мышью в другую группу. Календарь '
                        + 'пересоберётся сам. После первого сыгранного матча группы закрепляются.',
                },
                {
                    requires: hasTournament,
                    target: '#resetCategoryBtn',
                    modals: WORKSPACE,
                    entryTab: 'scheme',
                    optional: true,
                    title: 'Сбросить результаты',
                    text: 'Удаляет календарь, счета и протоколы категории, чтобы собрать турнир заново. '
                        + 'Заявки остаются. Пользуйтесь осторожно.',
                },
                {
                    requires: hasTournament,
                    target: '#openScheduleBtn',
                    modals: WORKSPACE,
                    entryTab: 'matches',
                    title: 'Шаг 3. Расставить по времени',
                    text: 'Система разложит матчи по дням и полям — подробнее в следующей главе.',
                },
                {
                    requires: hasTournament,
                    target: '#matchBoard .standings-table',
                    modals: WORKSPACE,
                    entryTab: 'matches',
                    optional: true,
                    title: 'Таблица группы',
                    text: 'Считается сама по счёту матчей. <b>Зелёное место</b> — команда выходит в плей-офф. '
                        + '«Форма» — последние матчи: В — победа, Н — ничья, П — поражение.',
                },
                {
                    requires: hasTournament,
                    target: '#matchBoard .match-row',
                    fallback: '#matchBoard',
                    modals: WORKSPACE,
                    entryTab: 'matches',
                    title: 'Внесите счёт',
                    text: 'Впишите голы обеих команд — счёт сохраняется сам, таблица пересчитывается. '
                        + 'Здесь же можно поправить время и стадион матча.',
                },
                {
                    requires: hasTournament,
                    target: '#matchBoard .match-protocol',
                    modals: WORKSPACE,
                    entryTab: 'matches',
                    optional: true,
                    title: 'Протокол матча',
                    text: 'После счёта становится активной эта кнопка: отметьте, кто играл, кто забил '
                        + 'и кто получил карточки. Из протоколов строится список бомбардиров.',
                },
                {
                    requires: hasTournament,
                    target: '#playoffBoard',
                    modals: WORKSPACE,
                    entryTab: 'playoff',
                    title: 'Шаг 4. Плей-офф',
                    text: 'Сетка заполняется <b>сама</b>: когда группа доиграна, в неё встают лучшие. '
                        + 'Победитель матча автоматически переходит дальше.',
                    tip: 'Ничья? Впишите серию пенальти в поля «пен.» — так определится, кто прошёл.',
                },
                {
                    requires: hasTournament,
                    target: '#awardsBoard',
                    fallback: '#playersBoard',
                    modals: WORKSPACE,
                    entryTab: 'players',
                    title: 'Шаг 5. Игроки и награды',
                    text: 'Бомбардиры, вратари и Fair Play считаются из протоколов. Расчётные призы система '
                        + 'предлагает сама, «Лучшего игрока» выбираете вы. Для каждого приза есть обложка для соцсетей.',
                },
                {
                    requires: hasTournament,
                    target: '#screenLink',
                    modals: WORKSPACE,
                    entryTab: 'players',
                    title: 'Табло для стадиона',
                    text: 'Откройте на телевизоре или проекторе — таблицы, сетка и бомбардиры будут '
                        + 'сменяться сами.',
                },
            ],
        },
        {
            key: 'roster',
            title: 'Состав по категориям',
            icon: 'users-round',
            steps: [
                {
                    requires: () => !hasEntry(),
                    title: 'Сначала заявите команду',
                    text: 'Состав по категориям открывается у заявленной команды. Заявите клуб в турнир '
                        + 'и пройдите эту главу снова.',
                },
                {
                    requires: hasEntry,
                    target: '#rosterBoard',
                    modals: [...WORKSPACE, 'rosterModal'],
                    title: 'Зачем это окно',
                    text: 'Игроки клуба заводятся один раз, а играть могут в разных категориях. '
                        + 'Здесь видно, кто где играет, и сколько игроков ещё ждут решения.',
                },
                {
                    requires: hasEntry,
                    target: '#rosterBoard .roster-column.free',
                    modals: [...WORKSPACE, 'rosterModal'],
                    title: 'Не распределены',
                    text: 'Сюда попадают игроки, которым подходят две категории (A и B одного возраста). '
                        + 'Внизу — те, кто не подходит никуда: нет даты рождения или не тот возраст.',
                },
                {
                    requires: hasEntry,
                    target: '#rosterBoard .roster-column:not(.free)',
                    modals: [...WORKSPACE, 'rosterModal'],
                    title: 'Колонка категории',
                    text: 'Игроки этой заявки. Если по году рождения подходит одна категория, система ставит '
                        + 'игрока сама — у него метка <b>«авто»</b>.',
                },
                {
                    requires: hasEntry,
                    target: '#rosterBoard .roster-player',
                    fallback: '#rosterBoard',
                    modals: [...WORKSPACE, 'rosterModal'],
                    title: 'Как перенести игрока',
                    text: 'Перетащите карточку мышью в нужную колонку (на телефоне — удержите палец) '
                        + 'или выберите категорию в списке на карточке. Куда нельзя по возрасту, '
                        + 'колонка подсветится красным.',
                    tip: 'Один игрок — одна категория. Кто уже сыграл матч, перенести нельзя.',
                },
                {
                    requires: hasEntry,
                    target: '#rosterPlayUpField',
                    modals: [...WORKSPACE, 'rosterModal'],
                    title: 'Младшие за старших',
                    text: 'Если по регламенту младшим можно играть за старших, включите это правило: '
                        + 'игрок 2012 г.р. сможет выйти за 2010-2011. Старшим за младших — нельзя никогда.',
                },
                {
                    requires: hasEntry,
                    target: '#rosterOpenTeam',
                    modals: [...WORKSPACE, 'rosterModal'],
                    title: 'Добавить игроков',
                    text: 'Нет нужного игрока? Откройте состав клуба и добавьте его — '
                        + 'он сразу появится здесь.',
                },
            ],
        },
        {
            key: 'schedule',
            title: 'Расписание матчей',
            icon: 'calendar-clock',
            steps: [
                {
                    requires: hasTournament,
                    target: field('#scheduleStartDate'),
                    modals: [...WORKSPACE, 'scheduleModal'],
                    title: 'Начало',
                    text: 'Дата и время первого матча. По умолчанию — из карточки турнира.',
                },
                {
                    requires: hasTournament,
                    target: field('#scheduleEndTime'),
                    modals: [...WORKSPACE, 'scheduleModal'],
                    title: 'Конец игрового дня',
                    text: 'Что не поместилось — перенесётся на следующий день.',
                },
                {
                    requires: hasTournament,
                    target: field('#scheduleDuration'),
                    modals: [...WORKSPACE, 'scheduleModal'],
                    title: 'Длительность и перерыв',
                    text: 'Сколько минут длится матч и сколько нужно между матчами на одном поле.',
                },
                {
                    requires: hasTournament,
                    target: field('#schedulePitches'),
                    modals: [...WORKSPACE, 'scheduleModal'],
                    title: 'Сколько полей',
                    text: 'Сколько матчей можно играть одновременно. Команда никогда не играет два матча сразу '
                        + 'и по возможности отдыхает между играми.',
                },
                {
                    requires: hasTournament,
                    target: field('#scheduleStadium'),
                    modals: [...WORKSPACE, 'scheduleModal'],
                    title: 'Стадион',
                    text: 'Проставит выбранный стадион всем расставленным матчам.',
                },
                {
                    requires: hasTournament,
                    target: field('#scheduleOnlyCurrent'),
                    modals: [...WORKSPACE, 'scheduleModal'],
                    title: 'Весь турнир или категория',
                    text: 'Лучше расставлять весь турнир сразу — тогда категории не займут одно поле в одно время.',
                },
                {
                    requires: hasTournament,
                    target: field('#scheduleOverwrite'),
                    modals: [...WORKSPACE, 'scheduleModal'],
                    title: 'Перезаписать время',
                    text: 'Без галочки уже расставленные матчи не трогаются. С галочкой — расписание '
                        + 'составится заново (сыгранные матчи не двигаются никогда).',
                },
                {
                    requires: hasTournament,
                    target: '#runScheduleBtn',
                    modals: [...WORKSPACE, 'scheduleModal'],
                    title: 'Расставить',
                    text: 'Плей-офф всегда ставится после групп. Любое время потом можно поправить вручную.',
                },
            ],
        },
        {
            key: 'protocol',
            title: 'Протокол матча',
            icon: 'clipboard-list',
            steps: [
                {
                    requires: () => !hasTournament(),
                    title: 'Нужен турнир со сыгранным матчем',
                    text: 'Протокол заполняется у сыгранного матча. Создайте турнир, внесите счёт '
                        + 'хотя бы одного матча и пройдите эту главу снова.',
                },
                {
                    requires: hasTournament,
                    target: '#matchBoard .match-protocol:not([disabled])',
                    fallback: '#matchBoard',
                    modals: WORKSPACE,
                    entryTab: 'matches',
                    title: 'Где открыть протокол',
                    text: 'Кнопка с планшетом справа от счёта. Она активна, когда у матча уже есть счёт.',
                },
                {
                    requires: () => hasTournament() && !playedMatchId(),
                    title: 'Протокол — после счёта',
                    text: 'Протокол открывается у сыгранного матча кнопкой с планшетом справа от счёта. '
                        + 'Внесите счёт хотя бы одного матча и пройдите эту главу снова.',
                },
                {
                    requires: playedMatchId,
                    target: '#protocolGrid',
                    modals: [...WORKSPACE, 'matchProtocolModal'],
                    title: 'Кто вышел на поле',
                    text: 'Отметьте игроков обеих команд, которые играли. Перчаткой отметьте вратаря — '
                        + 'по одному на команду.',
                },
                {
                    requires: playedMatchId,
                    target: '[data-add-event="goal"]',
                    modals: [...WORKSPACE, 'matchProtocolModal'],
                    title: 'Голы',
                    text: 'Добавьте каждый гол: команда, автор, минута, ассистент. Есть отметки «пенальти» '
                        + 'и «автогол» — автогол не идёт игроку в бомбардиры.',
                },
                {
                    requires: playedMatchId,
                    target: '[data-add-event="card"]',
                    modals: [...WORKSPACE, 'matchProtocolModal'],
                    title: 'Карточки',
                    text: 'Жёлтые и красные. Они считаются в таблице Fair Play.',
                },
                {
                    requires: playedMatchId,
                    target: '#protocolBalance',
                    modals: [...WORKSPACE, 'matchProtocolModal'],
                    title: 'Сверка со счётом',
                    text: 'Голов в протоколе должно быть ровно столько, сколько в счёте матча, '
                        + 'иначе сохранить не получится.',
                },
                {
                    requires: playedMatchId,
                    target: '#saveProtocolBtn',
                    modals: [...WORKSPACE, 'matchProtocolModal'],
                    title: 'Сохранить протокол',
                    text: 'Бомбардиры, вратари и награды пересчитаются автоматически.',
                },
            ],
        },
        {
            key: 'studio',
            title: 'Картинки для соцсетей',
            icon: 'image-plus',
            steps: [
                {
                    requires: () => !hasTournament(),
                    title: 'Нужен турнир',
                    text: 'Картинки делаются внутри турнира кнопкой «Публикация». Создайте турнир и вернитесь.',
                },
                {
                    requires: hasTournament,
                    target: '#openStudioBtn',
                    modals: WORKSPACE,
                    title: 'Публикация',
                    text: 'Готовые картинки для Telegram и Instagram: анонс, матч, таблица, итоги, награды.',
                },
                {
                    requires: hasTournament,
                    target: '#studioTemplates',
                    modals: [...WORKSPACE, 'postStudioModal'],
                    title: 'Что публикуем',
                    text: 'Выберите шаблон. Для «Матча», «Таблицы» или «Награды» ниже появится выбор, '
                        + 'какой именно.',
                },
                {
                    requires: hasTournament,
                    target: field('#studioFormat'),
                    modals: [...WORKSPACE, 'postStudioModal'],
                    title: 'Формат и категория',
                    text: 'Квадрат для ленты, вертикаль для сторис. Рядом — возрастная категория.',
                },
                {
                    requires: hasTournament,
                    target: field('#studioTheme'),
                    modals: [...WORKSPACE, 'postStudioModal'],
                    title: 'Оформление',
                    text: 'Тема (светлая или тёмная), шрифт и акцентный цвет — под стиль вашего клуба.',
                },
                {
                    requires: hasTournament,
                    target: '#studioBackgrounds',
                    modals: [...WORKSPACE, 'postStudioModal'],
                    title: 'Фон',
                    text: 'Афиша турнира, однотонный или своя картинка. Ползунок затемнения делает текст читаемым.',
                },
                {
                    requires: hasTournament,
                    target: field('#studioTitle'),
                    modals: [...WORKSPACE, 'postStudioModal'],
                    title: 'Свои подписи',
                    text: 'Пустые поля заполнятся из турнира. Впишите своё, если нужно: '
                        + 'например, «Вход свободный».',
                },
                {
                    requires: hasTournament,
                    target: '#studioCanvas',
                    modals: [...WORKSPACE, 'postStudioModal'],
                    title: 'Предпросмотр',
                    text: 'Это готовая картинка — то, что вы увидите, и будет в файле.',
                },
                {
                    requires: hasTournament,
                    target: '#studioDownload',
                    modals: [...WORKSPACE, 'postStudioModal'],
                    title: 'Скачать',
                    text: 'Сохраните PNG и публикуйте.',
                },
            ],
        },
        {
            key: 'finish',
            title: 'Итог',
            icon: 'graduation-cap',
            steps: [
                {
                    title: 'Вы прошли урок!',
                    text: 'Порядок работы:<ol class="tour-recap">'
                        + '<li>Стадионы и команды (один раз)</li>'
                        + '<li>Создать турнир и категории</li>'
                        + '<li>Заявить команды → «Подтвердила»</li>'
                        + '<li>Схема → «Жеребьёвка и календарь»</li>'
                        + '<li>Расставить по времени</li>'
                        + '<li>Вносить счёт и протоколы</li>'
                        + '<li>Плей-офф заполнится сам</li>'
                        + '<li>Награды и картинки</li></ol>'
                        + 'Урок всегда под рукой: кнопка <b>«Обучение»</b> и <b>«?»</b> в каждом окне.',
                },
            ],
        },
    ];

    /* С какой главы начинать, если «?» нажали в окне. */
    const MODAL_CHAPTER = {
        tournamentModal: 'create',
        stadiumModal: 'stadium',
        stadiumImportModal: 'stadium',
        teamModal: 'team',
        teamDetailsModal: 'team',
        memberModal: 'team',
        teamShareModal: 'team',
        scheduleModal: 'schedule',
        rosterModal: 'roster',
        matchProtocolModal: 'protocol',
        postStudioModal: 'studio',
        tournamentEntriesModal: 'manage',
    };

    /* --- Движок --- */

    const state = {
        steps: [],
        index: 0,
        opened: new Set(),
        frame: null,
        target: null,
        active: false,
        busy: false,
    };

    const ui = {};

    function el(tag, className, html) {
        const node = document.createElement(tag);
        if (className) node.className = className;
        if (html !== undefined) node.innerHTML = html;
        return node;
    }

    function buildUi() {
        if (ui.root) return;
        ui.root = el('div', 'tour-root');
        ui.root.id = 'tourRoot';
        ui.root.hidden = true;
        ui.blocker = el('div', 'tour-blocker');
        ui.spot = el('div', 'tour-spot');
        ui.tip = el('div', 'tour-tip');
        ui.tip.setAttribute('role', 'dialog');
        ui.tip.setAttribute('aria-live', 'polite');
        ui.root.append(ui.blocker, ui.spot, ui.tip);
        document.body.appendChild(ui.root);

        ui.tip.addEventListener('click', (event) => {
            const action = event.target.closest('[data-tour]')?.dataset.tour;
            if (action === 'next') go(state.index + 1);
            if (action === 'prev') go(state.index - 1, -1);
            if (action === 'close') finish(false);
            if (action === 'menu') { finish(false); openMenu(); }
        });
        ui.blocker.addEventListener('click', () => ui.tip.querySelector('[data-tour="next"]')?.focus());
        document.addEventListener('keydown', (event) => {
            if (!state.active) return;
            if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); finish(false); }
            if (event.key === 'ArrowRight' || event.key === 'Enter') { event.preventDefault(); go(state.index + 1); }
            if (event.key === 'ArrowLeft') { event.preventDefault(); go(state.index - 1, -1); }
        }, true);
    }

    function isVisible(node) {
        return Boolean(node && node.isConnected && node.getClientRects().length
            && getComputedStyle(node).visibility !== 'hidden');
    }

    function resolve(target) {
        if (!target) return null;
        const node = typeof target === 'function' ? target() : document.querySelector(target);
        return isVisible(node) ? node : null;
    }

    async function waitForTarget(step) {
        if (!step.target) return null;
        for (let attempt = 0; attempt < 25; attempt += 1) {
            const node = resolve(step.target) || resolve(step.fallback);
            if (node) return node;
            await new Promise((done) => window.setTimeout(done, 80));
        }
        return null;
    }

    async function prepare(step) {
        const need = step.modals || [];
        // Закрываем окна, которые открыл тур и которые этому шагу не нужны (с конца — верхние первыми).
        [...state.opened].reverse().forEach((id) => {
            if (!need.includes(id)) {
                closeModal(id);
                state.opened.delete(id);
            }
        });
        if (step.tab) switchTab(step.tab);
        for (const id of need) {
            const modal = byId(id);
            if (modal && modal.hidden && OPENERS[id]) {
                await OPENERS[id]();
                if (!byId(id).hidden) state.opened.add(id);
            }
        }
        if (step.entryTab && !byId('tournamentEntriesModal').hidden) {
            switchEntryTab(step.entryTab);
            renderSteps();
            if (step.entryTab === 'players') await loadPlayers();
        }
    }

    function chapterOf(step) {
        return CHAPTERS.find((chapter) => chapter.steps.includes(step));
    }

    async function go(index, direction = 1) {
        if (state.busy) return;
        if (index >= state.steps.length) { finish(true); return; }
        if (index < 0) return;
        state.busy = true;
        try {
            let next = index;
            // Шаги, для которых сейчас нет данных, пропускаем в сторону движения.
            while (next >= 0 && next < state.steps.length) {
                const step = state.steps[next];
                if (!step.requires || step.requires()) {
                    await prepare(step);
                    const node = await waitForTarget(step);
                    if (node || !step.target || !step.optional) {
                        state.index = next;
                        show(step, node);
                        return;
                    }
                }
                next += direction;
            }
            if (next >= state.steps.length) finish(true);
        } catch (error) {
            console.error('Обучение:', error);
            finish(false);
        } finally {
            state.busy = false;
        }
    }

    function progressText() {
        const total = state.steps.filter((step) => !step.requires || step.requires()).length;
        const done = state.steps.slice(0, state.index + 1)
            .filter((step) => !step.requires || step.requires()).length;
        return { done, total };
    }

    function show(step, node) {
        state.target = node;
        const chapter = chapterOf(step);
        const { done, total } = progressText();
        const last = state.index >= state.steps.length - 1;
        ui.tip.innerHTML = `
            <div class="tour-tip-head">
                <span class="tour-chapter"><i data-lucide="${chapter.icon}"></i>${escapeHtml(chapter.title)}</span>
                <button type="button" class="tour-x" data-tour="close" aria-label="Закрыть обучение">&times;</button>
            </div>
            <h3>${escapeHtml(step.title)}</h3>
            <div class="tour-text">${step.text}</div>
            ${step.tip ? `<div class="tour-hint"><i data-lucide="lightbulb"></i><span>${escapeHtml(step.tip)}</span></div>` : ''}
            <div class="tour-progress"><span style="width:${Math.round((done / total) * 100)}%"></span></div>
            <div class="tour-foot">
                <button type="button" class="tour-link" data-tour="menu">Оглавление</button>
                <span class="tour-count">${done} / ${total}</span>
                <button type="button" class="tour-btn ghost" data-tour="prev" ${state.index === 0 ? 'disabled' : ''}>Назад</button>
                <button type="button" class="tour-btn" data-tour="next">${last ? 'Готово' : 'Далее'}</button>
            </div>`;
        refreshIcons();
        ui.root.hidden = false;
        ui.root.classList.toggle('no-target', !node);
        if (node) node.scrollIntoView({ block: 'center', inline: 'nearest', behavior: 'smooth' });
        ui.tip.classList.remove('tour-enter');
        void ui.tip.offsetWidth;
        ui.tip.classList.add('tour-enter');
        ui.tip.querySelector('[data-tour="next"]').focus({ preventScroll: true });
        place();
    }

    function place() {
        const pad = 6;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const node = state.target;
        if (!node || !isVisible(node)) {
            ui.spot.style.cssText = `left:${vw / 2}px;top:${vh / 2}px;width:0;height:0;`;
            ui.tip.style.cssText = '';
            ui.tip.dataset.side = 'center';
            return;
        }
        const rect = node.getBoundingClientRect();
        const box = {
            left: Math.max(4, rect.left - pad),
            top: Math.max(4, rect.top - pad),
            right: Math.min(vw - 4, rect.right + pad),
            bottom: Math.min(vh - 4, rect.bottom + pad),
        };
        ui.spot.style.cssText = `left:${box.left}px;top:${box.top}px;`
            + `width:${Math.max(0, box.right - box.left)}px;height:${Math.max(0, box.bottom - box.top)}px;`;

        if (vw < 640) {
            // На телефоне подсказка всегда внизу или вверху экрана, напротив подсветки.
            ui.tip.dataset.side = rect.top + rect.height / 2 > vh / 2 ? 'sheet-top' : 'sheet-bottom';
            ui.tip.style.cssText = '';
            return;
        }
        const tipRect = ui.tip.getBoundingClientRect();
        const gap = 14;
        const options = [
            ['bottom', box.left, box.bottom + gap, vh - box.bottom - gap >= tipRect.height],
            ['top', box.left, box.top - gap - tipRect.height, box.top - gap >= tipRect.height],
            ['right', box.right + gap, box.top, vw - box.right - gap >= tipRect.width],
            ['left', box.left - gap - tipRect.width, box.top, box.left - gap >= tipRect.width],
        ];
        const [side, rawX, rawY] = options.find((option) => option[3]) || ['over', vw - tipRect.width - 16, vh - tipRect.height - 16];
        const x = Math.min(Math.max(12, rawX), vw - tipRect.width - 12);
        const y = Math.min(Math.max(12, rawY), vh - tipRect.height - 12);
        ui.tip.dataset.side = side;
        ui.tip.style.cssText = `left:${x}px;top:${y}px;`;
    }

    function loop() {
        if (!state.active) return;
        place();
        state.frame = window.requestAnimationFrame(loop);
    }

    function start(chapterKeys, fromModal) {
        buildUi();
        closeMenu();
        hideInvite();
        const keys = chapterKeys && chapterKeys.length ? chapterKeys : CHAPTERS.map((chapter) => chapter.key);
        state.steps = CHAPTERS.filter((chapter) => keys.includes(chapter.key)).flatMap((chapter) => chapter.steps);
        state.opened = new Set();
        state.active = true;
        document.body.classList.add('tour-active');
        state.frame = window.requestAnimationFrame(loop);
        // Из «?» внутри окна начинаем с первого шага про это окно, а не с кнопки, которая его открывает.
        const first = fromModal
            ? state.steps.findIndex((step) => (step.modals || []).includes(fromModal))
            : -1;
        go(Math.max(0, first));
    }

    function finish(completed) {
        if (!state.active) return;
        state.active = false;
        window.cancelAnimationFrame(state.frame);
        [...state.opened].reverse().forEach((id) => closeModal(id));
        state.opened.clear();
        ui.root.hidden = true;
        document.body.classList.remove('tour-active');
        saveProgress({ seen: true, completed: completed || readProgress().completed });
    }

    /* --- Оглавление урока --- */

    function readProgress() {
        try {
            return JSON.parse(window.localStorage.getItem(STORAGE_KEY) || '{}') || {};
        } catch (error) {
            return {};
        }
    }

    function saveProgress(patch) {
        try {
            window.localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...readProgress(), ...patch }));
        } catch (error) {
            /* приватный режим — просто не запоминаем */
        }
    }

    function openMenu() {
        buildUi();
        closeMenu();
        hideInvite();
        const lessons = CHAPTERS.filter((chapter) => chapter.key !== 'finish');
        const count = (chapter) => chapter.steps.filter((step) => !step.requires || step.requires()).length;
        const total = lessons.reduce((sum, chapter) => sum + count(chapter), 0);
        ui.menu = el('div', 'tour-menu-backdrop', `
            <div class="tour-menu" role="dialog" aria-modal="true" aria-labelledby="tourMenuTitle">
                <button type="button" class="tour-x" data-menu="close" aria-label="Закрыть">&times;</button>
                <span class="tour-chapter"><i data-lucide="graduation-cap"></i>Обучение</span>
                <h2 id="tourMenuTitle">Турниры за один урок</h2>
                <p>${total} коротких шагов, около ${Math.max(5, Math.round(total / 7))} минут. Подсветим каждое поле
                    и кнопку и объясним, что с ними делать. Ничего не сохраняется — можно смело листать.</p>
                <button type="button" class="tour-btn wide" data-menu="all">
                    <i data-lucide="play"></i> Пройти весь урок
                </button>
                <p class="tour-menu-sub">Или выберите тему:</p>
                <div class="tour-menu-list">
                    ${lessons.map((chapter, index) => `
                        <button type="button" data-menu="chapter" data-key="${chapter.key}">
                            <span class="tour-menu-no">${index + 1}</span>
                            <i data-lucide="${chapter.icon}"></i>
                            <span class="tour-menu-title">${escapeHtml(chapter.title)}</span>
                            <small>${count(chapter)} шаг.</small>
                        </button>`).join('')}
                </div>
            </div>`);
        ui.menu.id = 'tourMenu';
        document.body.appendChild(ui.menu);
        refreshIcons();
        ui.menu.querySelector('[data-menu="all"]').focus();
        ui.menu.addEventListener('click', (event) => {
            const button = event.target.closest('[data-menu]');
            if (event.target === ui.menu || button?.dataset.menu === 'close') { closeMenu(); return; }
            if (button?.dataset.menu === 'all') start();
            if (button?.dataset.menu === 'chapter') start([button.dataset.key]);
        });
        ui.menu.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') closeMenu();
        });
    }

    function closeMenu() {
        ui.menu?.remove();
        ui.menu = null;
    }

    /* --- Кнопки запуска: на странице и «?» в каждом окне --- */

    function addLaunchers() {
        // Шапка с заголовком на части экранов скрыта, а вкладки видны всегда.
        const header = byId('tournamentCatalogTabs');
        if (header && !header.querySelector('.tour-launch')) {
            const button = el('button', 'tour-launch', '<i data-lucide="graduation-cap"></i><span>Обучение</span>');
            button.type = 'button';
            button.id = 'tourLaunch';
            button.addEventListener('click', openMenu);
            header.appendChild(button);
        }
        Object.entries(MODAL_CHAPTER).forEach(([modalId, chapterKey]) => {
            const modal = byId(modalId);
            const head = modal?.querySelector('.tournament-catalog-modal-header');
            if (!head || head.querySelector('.tour-help')) return;
            const button = el('button', 'icon-button tour-help', '<i data-lucide="circle-help"></i>');
            button.type = 'button';
            button.title = 'Как пользоваться этим окном';
            button.setAttribute('aria-label', 'Обучение по этому окну');
            button.addEventListener('click', (event) => {
                event.stopPropagation();
                start([chapterKey], modalId);
            });
            const close = head.querySelector('[data-close-modal], [data-close-protocol]');
            if (close) close.before(button); else head.appendChild(button);
        });
        refreshIcons();
    }

    function hideInvite() {
        ui.invite?.remove();
        ui.invite = null;
    }

    function maybeInvite() {
        if (readProgress().seen) return;
        ui.invite = el('div', 'tour-invite', `
            <i data-lucide="graduation-cap"></i>
            <div>
                <strong>Впервые здесь?</strong>
                <span>Покажем всё по шагам: от создания турнира до плей-офф.</span>
            </div>
            <button type="button" class="tour-btn" data-invite="start">Начать урок</button>
            <button type="button" class="tour-link" data-invite="later">Позже</button>`);
        ui.invite.id = 'tourInvite';
        document.body.appendChild(ui.invite);
        refreshIcons();
        ui.invite.addEventListener('click', (event) => {
            const action = event.target.closest('[data-invite]')?.dataset.invite;
            if (action === 'start') openMenu();
            if (action === 'later') { saveProgress({ seen: true }); hideInvite(); }
        });
    }

    function init() {
        addLaunchers();
        window.setTimeout(maybeInvite, 1200);
    }

    window.TournamentTour = { start, openMenu, chapters: CHAPTERS };
    if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', init);
    else init();
})();
