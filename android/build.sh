#!/bin/bash
# Сборка FK Karasu.apk без Gradle: aapt2 → javac → d8 → zipalign → apksigner.
#   ./build.sh            → build/FK-Karasu.apk
#   DEBUG=true ./build.sh → с отладкой WebView через chrome://inspect (не раздавать)
# Версию поднимать в VERSION_CODE/VERSION_NAME, иначе телефон не даст обновить поверх.
# Ключ подписи хранится ВНЕ репозитория: ~/.fk-karasu-android/ (потеряете ключ —
# обновить установленное приложение не получится, только удалить и поставить заново).
set -euo pipefail
cd "$(dirname "$0")"

VERSION_CODE=1
VERSION_NAME=1.0

SDK="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
BT="$SDK/build-tools/$(ls "$SDK/build-tools" | sort -V | tail -1)"
PLATFORM="$SDK/platforms/$(ls "$SDK/platforms" | sort -V | tail -1)"
ANDROID_JAR="$PLATFORM/android.jar"
KEY_DIR="$HOME/.fk-karasu-android"
KEYSTORE="$KEY_DIR/release.jks"
OUT=build

rm -rf "$OUT"; mkdir -p "$OUT/gen/uz/karasu/admin" "$OUT/classes" "$OUT/dex"

if [ ! -f "$KEYSTORE" ]; then
  mkdir -p "$KEY_DIR"; chmod 700 "$KEY_DIR"
  openssl rand -base64 24 | tr -d '/+=' > "$KEY_DIR/password"
  chmod 600 "$KEY_DIR/password"
  keytool -genkeypair -keystore "$KEYSTORE" -alias fkkarasu -keyalg RSA -keysize 2048 \
    -validity 10000 -storepass "$(cat "$KEY_DIR/password")" -dname "CN=FK Karasu, O=FK Karasu, C=UZ"
fi

cat > "$OUT/gen/uz/karasu/admin/BuildConfig.java" <<JAVA
package uz.karasu.admin;
final class BuildConfig { static final String VERSION = "$VERSION_NAME"; static final boolean DEBUG = ${DEBUG:-false}; }
JAVA

"$BT/aapt2" compile --dir res -o "$OUT/res.zip"
"$BT/aapt2" link -I "$ANDROID_JAR" --manifest AndroidManifest.xml "$OUT/res.zip" \
  --java "$OUT/gen" --min-sdk-version 24 --target-sdk-version 34 \
  --version-code "$VERSION_CODE" --version-name "$VERSION_NAME" -o "$OUT/unsigned.apk"

javac -source 8 -target 8 -bootclasspath "$ANDROID_JAR" -classpath "$BT/core-lambda-stubs.jar" -encoding UTF-8 -nowarn -Xlint:-options \
  -d "$OUT/classes" $(find src "$OUT/gen" -name '*.java')
"$BT/d8" --release --min-api 24 --lib "$ANDROID_JAR" --output "$OUT/dex" $(find "$OUT/classes" -name '*.class')

(cd "$OUT/dex" && zip -q -j ../unsigned.apk classes.dex)
"$BT/zipalign" -f -p 4 "$OUT/unsigned.apk" "$OUT/aligned.apk"
"$BT/apksigner" sign --ks "$KEYSTORE" --ks-key-alias fkkarasu \
  --ks-pass "file:$KEY_DIR/password" --out "$OUT/FK-Karasu.apk" "$OUT/aligned.apk"
"$BT/apksigner" verify "$OUT/FK-Karasu.apk"
echo "Готово: $(pwd)/$OUT/FK-Karasu.apk (версия $VERSION_NAME)"
