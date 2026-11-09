# Hikvision Bridge / Karasu Bridge

Рабочие заметки по локальному bridge mini PC для терминалов Hikvision.

## Независимый camera-kiosk

Видеомониторинг запускается отдельным сервисом и не меняет работу Hikvision bridge,
терминалов, реле или посещений.

```bash
cd /home/admina/proAppFootballClub
cp bridge/run-camera-kiosk.example.sh bridge/run-camera-kiosk.sh
nano bridge/run-camera-kiosk.sh
chmod 700 bridge/run-camera-kiosk.sh
sudo bash bridge/install-camera-kiosk-service.sh
```

В `run-camera-kiosk.sh` нужно указать тот же `DEVICE_INGEST_KEY`, который использует
основной bridge. RTSP, FPS, разрешение и остальные параметры задаются в админке:
`Настройки -> Камера`. Camera-kiosk забирает их с сервера автоматически.

Локальная страница по умолчанию:

```text
http://192.168.1.5:8090
```

Проверка:

```bash
sudo systemctl status karasu-camera-kiosk.service
journalctl -u karasu-camera-kiosk.service -n 100 --no-pager
```

### Автозапуск на локальном мониторе

После установки camera-kiosk можно автоматически открывать его на подключенном
к mini PC мониторе в полноэкранном режиме:

```bash
bash bridge/install-camera-kiosk-browser.sh
sudo reboot
```

Установщик использует Chromium, Google Chrome или Firefox из системы. Страница
открывается локально по адресу `http://127.0.0.1:8090`, поэтому Tailscale для
подключенного к bridge монитора не нужен. Графический пользователь Ubuntu должен
автоматически входить в систему после загрузки, иначе браузер запустится только
после ручного входа.

На минимальной Ubuntu без рабочего стола установите легкий графический сеанс:

```bash
sudo apt update
sudo apt install -y xserver-xorg lightdm openbox dbus-x11
bash bridge/install-camera-kiosk-browser.sh
sudo reboot
```

При наличии LightDM и Openbox установщик включает графическую загрузку,
автоматический вход пользователя `admina` и запуск kiosk из Openbox.

## Что где находится

- Проект: `proAppFootballClub`
- Сайт: `https://karasu.uz` (домашний сервер, Coolify)
- GitHub: `https://github.com/Alisher1994/proAppFootballClub`
- Локальный mini PC hostname: `karasu-bridge`
- Пользователь SSH: `admina`
- Путь проекта на mini PC: `/home/admina/proAppFootballClub`
- Bridge файл: `/home/admina/proAppFootballClub/bridge/hikvision-school-bridge.mjs`
- systemd service: `karasu-school-bridge.service`

## IP адреса

- Mini PC внутри клуба: `192.168.1.5`
- Этот IP закреплен статически через netplan.
- Роутер / gateway: `192.168.1.1`
- DNS: `192.168.1.1`, `8.8.8.8`
- Внешний IP офиса на 2026-06-27: `84.54.84.117`
- Внешний IP может поменяться у провайдера, поэтому для доступа из дома лучше Tailscale/ZeroTier.

## Терминалы Hikvision

Настраиваются в админке:

`Настройки -> Hikvision`

Текущая схема:

- Вход: `192.168.1.8:443`
- Выход: `192.168.1.7:443`
- Протокол: `HTTPS`

Если IP терминалов поменялись, менять их надо в админке, не в коде.

## SSH внутри клуба

```bash
ssh admina@192.168.1.5
```

## Обновить bridge после изменений в GitHub

На mini PC:

```bash
cd /home/admina/proAppFootballClub
git pull --ff-only origin main
sudo systemctl restart karasu-school-bridge.service
sudo systemctl status karasu-school-bridge.service
```

Если статус открылся в просмотрщике, выйти клавишей `q`.

## Проверить bridge service

```bash
sudo systemctl status karasu-school-bridge.service
```

Логи:

```bash
journalctl -u karasu-school-bridge.service -n 100 --no-pager
```

Live-логи:

```bash
journalctl -u karasu-school-bridge.service -f
```

## Проверить сеть mini PC

Локальный IP:

```bash
hostname -I
ip -4 addr show enp1s0
ip route
```

Интернет / внешний IP:

```bash
curl -4 -s https://api.ipify.org
echo
```

Ожидаемо:

- `ip -4 addr show enp1s0` показывает `192.168.1.5/24`
- не должно быть слова `dynamic` для IPv4
- `ip route` показывает `default via 192.168.1.1 ... proto static`

## Netplan config

Файл:

```bash
/etc/netplan/00-installer-config.yaml
```

Текущий статический конфиг:

```yaml
network:
  version: 2
  ethernets:
    enp1s0:
      match:
        macaddress: 98:e7:f4:bd:71:d6
      set-name: enp1s0
      dhcp4: false
      dhcp6: true
      addresses:
        - 192.168.1.5/24
      routes:
        - to: default
          via: 192.168.1.1
      nameservers:
        addresses:
          - 192.168.1.1
          - 8.8.8.8
  wifis: {}
```

Проверить и применить:

```bash
sudo netplan try
sudo netplan apply
```

Если нужно откатить:

```bash
sudo cp /etc/netplan/00-installer-config.yaml.bak /etc/netplan/00-installer-config.yaml
sudo netplan apply
```

## Bridge key

Ключ bridge не записываем в документацию.

Где смотреть:

`Настройки -> Hikvision -> DEVICE_INGEST_KEY`

Этот ключ должен быть в запуске bridge на mini PC как `DEVICE_INGEST_KEY`.

## Настройки в админке Hikvision

В админке есть важные переключатели:

- `Параллельно записывать вход и выход`
  - Ускоряет запись.
  - Логи могут идти вперемешку, потому что оба терминала пишутся одновременно.
  - Внутри каждого терминала порядок записи остается последовательным.

- `Удалять из терминалов записи, которых нет в системе`
  - Включать для полной сверки.
  - Удаляет старые numeric-ID записи из терминалов, если ученика/сотрудника уже нет в базе.
  - Нужно для случаев, когда старый ученик был удален из системы, но остался в памяти терминала.

## Когда нужна полная синхронизация

Полная синхронизация нужна:

- после изменения IP терминалов;
- после включения очистки старых записей;
- если есть подозрение, что в терминалах остались старые люди;
- после долгого отключения терминалов;
- для плановой ночной сверки.

Обычные изменения ученика/сотрудника отправляются точечно:

- добавление ученика;
- изменение фото;
- оплата;
- блокировка/разблокировка;
- удаление ученика или сотрудника.

## Что значит "фото уже было в терминале"

Это не ошибка.

Bridge обновил пользователя, но Hikvision ответил, что фото лица уже есть в терминале. Если доступ разрешен, человек должен проходить.

## Удаленный доступ из дома через Tailscale

SSH наружу через роутер не открываем. Для удаленного доступа используется Tailscale.

Tailscale-устройство:

- Аккаунт: `Alisher1994`
- Mini PC: `karasu-bridge`
- Tailscale IP: `100.92.167.48`

Подключение из дома или с любого ноутбука:

```bash
ssh admina@100.92.167.48
```

На компьютере, с которого подключаемся, обязательно должен быть установлен и включен Tailscale, и вход должен быть выполнен в тот же аккаунт `Alisher1994`.

Для Windows:

1. Установить Tailscale: `https://tailscale.com/download/windows`
2. Войти через тот же GitHub/Tailscale аккаунт.
3. Проверить в PowerShell:

```powershell
tailscale status
ssh admina@100.92.167.48
```

Проверка на mini PC:

```bash
tailscale status
tailscale ip -4
```

Ожидаемый вывод:

```text
100.92.167.48  karasu-bridge  Alisher1994@  linux  -
100.92.167.48
```

Если Tailscale разлогинился:

```bash
sudo tailscale up --hostname karasu-bridge
```

Открыть ссылку `https://login.tailscale.com/a/...`, нажать `Connect`, затем снова проверить:

```bash
tailscale status
tailscale ip -4
```

Почему Tailscale:

- не нужен пароль от роутера;
- не нужен статический внешний IP;
- не важна смена внешнего IP офиса;
- SSH-порт mini PC не открыт в интернет.

## Удаленный доступ к веб-панели терминалов Hikvision

Терминалы `192.168.1.7` и `192.168.1.8` находятся только внутри сети клуба. Из дома к ним можно подключаться через SSH tunnel на bridge.

В проекте есть готовый файл:

```text
scripts/windows/open-hikvision-tunnel.bat
```

Запустить его двойным кликом на Windows-ноутбуке, где включен Tailscale. Пока окно `.bat` открыто, в браузере доступны:

- Вход: `https://localhost:8448`
- Выход: `https://localhost:8447`

Если запускать вручную:

```powershell
ssh -N -L 8447:192.168.1.7:443 -L 8448:192.168.1.8:443 admina@100.92.167.48
```

Окно SSH/tunnel нужно держать открытым. Закрыли окно - доступ к терминалам через `localhost` пропал.
