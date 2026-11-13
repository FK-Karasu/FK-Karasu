package uz.karasu.admin;

import android.Manifest;
import android.app.Activity;
import android.app.DownloadManager;
import android.content.ActivityNotFoundException;
import android.content.ContentValues;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.graphics.Bitmap;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.os.Environment;
import android.provider.MediaStore;
import android.util.Base64;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.JavascriptInterface;
import android.webkit.URLUtil;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceError;
import android.webkit.WebResourceRequest;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import android.widget.FrameLayout;
import android.widget.ProgressBar;
import android.widget.Toast;

import java.io.File;
import java.io.FileOutputStream;
import java.io.OutputStream;
import java.util.ArrayList;

/**
 * Приложение FK Karasu: открывает https://karasu.uz во встроенном браузере.
 *
 * Кроме самого сайта умеет то, чего WebView по умолчанию не делает:
 * выбор фото (галерея или камера), скачивание PDF/Excel и картинок из «Студии»,
 * кнопку «Назад», внешние ссылки (Telegram, телефон) и экран «нет связи».
 */
public class MainActivity extends Activity {
    private static final String HOME = "https://karasu.uz/";
    private static final int REQ_FILE = 1;
    private static final int REQ_STORAGE = 2;

    private WebView web;
    private ProgressBar progress;
    private ValueCallback<Uri[]> fileCallback;
    private Uri cameraUri;
    private String failedUrl;

    // Файл, ожидающий разрешения на запись (только Android 9 и старше).
    private byte[] pendingBytes;
    private String pendingName;
    private String pendingMime;

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);

        FrameLayout root = new FrameLayout(this);
        root.setBackgroundColor(Color.parseColor("#F4F1EE"));
        web = new WebView(this);
        root.addView(web, new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.MATCH_PARENT));
        progress = new ProgressBar(this, null, android.R.attr.progressBarStyleHorizontal);
        progress.setMax(100);
        progress.setProgressTintList(android.content.res.ColorStateList.valueOf(Color.parseColor("#FF8A00")));
        FrameLayout.LayoutParams barParams = new FrameLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, dp(3));
        root.addView(progress, barParams);
        setContentView(root);

        if (BuildConfig.DEBUG) WebView.setWebContentsDebuggingEnabled(true);
        setupWebView();

        if (state != null && web.restoreState(state) != null) return;
        web.loadUrl(startUrl(getIntent()));
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }

    private String startUrl(Intent intent) {
        Uri data = intent != null ? intent.getData() : null;
        if (data != null && isOwnHost(data)) return data.toString();
        return HOME;
    }

    private static boolean isOwnHost(Uri uri) {
        String host = uri.getHost();
        if (host == null) return false;
        host = host.toLowerCase();
        return host.equals("karasu.uz") || host.endsWith(".karasu.uz");
    }

    private void setupWebView() {
        WebSettings s = web.getSettings();
        s.setJavaScriptEnabled(true);
        s.setDomStorageEnabled(true);
        s.setDatabaseEnabled(true);
        s.setLoadWithOverviewMode(true);
        s.setUseWideViewPort(true);
        s.setSupportZoom(false);
        s.setBuiltInZoomControls(false);
        s.setMediaPlaybackRequiresUserGesture(false);
        s.setAllowFileAccess(false);
        s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        s.setTextZoom(100);
        s.setSupportMultipleWindows(false); // window.open(...) открывается здесь же
        s.setUserAgentString(s.getUserAgentString() + " FKKarasuApp/" + BuildConfig.VERSION);

        CookieManager cookies = CookieManager.getInstance();
        cookies.setAcceptCookie(true);
        cookies.setAcceptThirdPartyCookies(web, true);

        web.addJavascriptInterface(new Bridge(), "FKKarasuApp");
        web.setWebViewClient(new Client());
        web.setWebChromeClient(new Chrome());
        web.setDownloadListener((url, userAgent, disposition, mime, length) -> download(url, userAgent, disposition, mime));
    }

    // ---------- Навигация ----------

    private class Client extends WebViewClient {
        @Override
        public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
            Uri uri = request.getUrl();
            String scheme = uri.getScheme() == null ? "" : uri.getScheme().toLowerCase();
            if ((scheme.equals("https") || scheme.equals("http")) && isOwnHost(uri)) return false;
            openExternal(uri);
            return true;
        }

        @Override
        public void onPageStarted(WebView view, String url, Bitmap favicon) {
            progress.setVisibility(View.VISIBLE);
        }

        @Override
        public void onPageFinished(WebView view, String url) {
            progress.setVisibility(View.GONE);
            CookieManager.getInstance().flush();
            view.evaluateJavascript(DOWNLOAD_HOOK, null);
            view.evaluateJavascript(APP_CSS, null);
        }

        @Override
        public void onReceivedError(WebView view, WebResourceRequest request, WebResourceError error) {
            if (!request.isForMainFrame()) return;
            failedUrl = request.getUrl().toString();
            view.loadDataWithBaseURL(null, OFFLINE_PAGE, "text/html", "utf-8", null);
        }
    }

    private void openExternal(Uri uri) {
        try {
            Intent intent;
            if ("intent".equals(uri.getScheme())) {
                intent = Intent.parseUri(uri.toString(), Intent.URI_INTENT_SCHEME);
            } else {
                intent = new Intent(Intent.ACTION_VIEW, uri);
            }
            intent.addCategory(Intent.CATEGORY_BROWSABLE);
            startActivity(intent);
        } catch (Exception e) {
            toast("Не удалось открыть ссылку");
        }
    }

    private class Chrome extends WebChromeClient {
        @Override
        public void onProgressChanged(WebView view, int newProgress) {
            progress.setProgress(newProgress);
            progress.setVisibility(newProgress >= 100 ? View.GONE : View.VISIBLE);
        }

        @Override
        public boolean onShowFileChooser(WebView view, ValueCallback<Uri[]> callback, FileChooserParams params) {
            if (fileCallback != null) fileCallback.onReceiveValue(null);
            fileCallback = callback;
            return openFileChooser(params);
        }
    }

    @Override
    public void onBackPressed() {
        if (failedUrl != null) {
            retry();
        } else if (web.canGoBack()) {
            web.goBack();
        } else {
            super.onBackPressed();
        }
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        if (intent.getData() != null && isOwnHost(intent.getData())) web.loadUrl(intent.getData().toString());
    }

    @Override
    protected void onSaveInstanceState(Bundle out) {
        super.onSaveInstanceState(out);
        web.saveState(out);
    }

    @Override
    protected void onPause() {
        super.onPause();
        CookieManager.getInstance().flush();
    }

    private void retry() {
        String url = failedUrl != null ? failedUrl : HOME;
        failedUrl = null;
        web.loadUrl(url);
    }

    // ---------- Выбор файлов и камера ----------

    private boolean openFileChooser(WebChromeClient.FileChooserParams params) {
        Intent pick;
        try {
            pick = params.createIntent();
        } catch (Exception e) {
            pick = new Intent(Intent.ACTION_GET_CONTENT).setType("*/*").addCategory(Intent.CATEGORY_OPENABLE);
        }
        if (params.getMode() == WebChromeClient.FileChooserParams.MODE_OPEN_MULTIPLE) {
            pick.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        }

        ArrayList<Intent> extra = new ArrayList<>();
        cameraUri = null;
        if (acceptsImages(params) && Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            try {
                ContentValues values = new ContentValues();
                values.put(MediaStore.Images.Media.DISPLAY_NAME, "karasu_" + System.currentTimeMillis() + ".jpg");
                values.put(MediaStore.Images.Media.MIME_TYPE, "image/jpeg");
                values.put(MediaStore.Images.Media.RELATIVE_PATH, Environment.DIRECTORY_PICTURES + "/FK Karasu");
                cameraUri = getContentResolver().insert(MediaStore.Images.Media.EXTERNAL_CONTENT_URI, values);
                if (cameraUri != null) {
                    Intent camera = new Intent(MediaStore.ACTION_IMAGE_CAPTURE);
                    camera.putExtra(MediaStore.EXTRA_OUTPUT, cameraUri);
                    camera.addFlags(Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
                    if (camera.resolveActivity(getPackageManager()) != null) extra.add(camera);
                }
            } catch (Exception ignored) {
                cameraUri = null;
            }
        }

        Intent chooser = Intent.createChooser(pick, "Выберите файл");
        if (!extra.isEmpty()) chooser.putExtra(Intent.EXTRA_INITIAL_INTENTS, extra.toArray(new Intent[0]));
        try {
            startActivityForResult(chooser, REQ_FILE);
            return true;
        } catch (ActivityNotFoundException e) {
            dropCameraUri();
            fileCallback = null;
            toast("Нет приложения для выбора файлов");
            return false;
        }
    }

    private static boolean acceptsImages(WebChromeClient.FileChooserParams params) {
        String[] types = params.getAcceptTypes();
        if (types == null || types.length == 0) return true;
        for (String t : types) {
            if (t == null || t.isEmpty() || t.startsWith("image") || t.equals("*/*")) return true;
            if (t.matches("(?i).*\\.(jpe?g|png|webp|heic)")) return true;
        }
        return false;
    }

    private void dropCameraUri() {
        if (cameraUri != null) {
            try { getContentResolver().delete(cameraUri, null, null); } catch (Exception ignored) { }
            cameraUri = null;
        }
    }

    private boolean cameraShotSaved() {
        if (cameraUri == null) return false;
        try (android.content.res.AssetFileDescriptor fd =
                     getContentResolver().openAssetFileDescriptor(cameraUri, "r")) {
            return fd != null && fd.getLength() > 0;
        } catch (Exception e) {
            return false;
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (requestCode != REQ_FILE || fileCallback == null) return;

        Uri[] result = null;
        if (resultCode == RESULT_OK) {
            if (data != null && data.getClipData() != null) {
                int n = data.getClipData().getItemCount();
                result = new Uri[n];
                for (int i = 0; i < n; i++) result[i] = data.getClipData().getItemAt(i).getUri();
            } else if (data != null && data.getData() != null) {
                result = new Uri[]{data.getData()};
            } else if (cameraShotSaved()) {
                result = new Uri[]{cameraUri};
                cameraUri = null; // фото оставляем в галерее
            }
        }
        dropCameraUri();
        fileCallback.onReceiveValue(result);
        fileCallback = null;
    }

    // ---------- Скачивание ----------

    /** PDF, Excel и другие файлы с сервера: через системный менеджер загрузок, с cookie сессии. */
    private void download(String url, String userAgent, String disposition, String mime) {
        if (url.startsWith("blob:") || url.startsWith("data:")) {
            // Такие ссылки перехватывает DOWNLOAD_HOOK; сюда попадаем, если ссылку открыли иначе.
            web.evaluateJavascript("window.__fkSaveUrl && window.__fkSaveUrl(" + jsString(url) + ", '', '')", null);
            return;
        }
        try {
            String name = URLUtil.guessFileName(url, disposition, mime);
            DownloadManager.Request req = new DownloadManager.Request(Uri.parse(url));
            String cookie = CookieManager.getInstance().getCookie(url);
            if (cookie != null) req.addRequestHeader("Cookie", cookie);
            req.addRequestHeader("User-Agent", userAgent);
            if (mime != null) req.setMimeType(mime);
            req.setTitle(name);
            req.setNotificationVisibility(DownloadManager.Request.VISIBILITY_VISIBLE_NOTIFY_COMPLETED);
            req.setDestinationInExternalPublicDir(Environment.DIRECTORY_DOWNLOADS, name);
            DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
            dm.enqueue(req);
            toast("Скачивание: " + name);
        } catch (Exception e) {
            openExternal(Uri.parse(url));
        }
    }

    private static String jsString(String value) {
        return "'" + value.replace("\\", "\\\\").replace("'", "\\'") + "'";
    }

    /** Файлы, которые сайт собирает прямо в браузере (картинки «Студии», CSV, табель). */
    private class Bridge {
        @JavascriptInterface
        public void saveBase64(String base64, String name, String mime) {
            final byte[] bytes;
            try {
                bytes = Base64.decode(base64, Base64.DEFAULT);
            } catch (Exception e) {
                runOnUiThread(() -> toast("Не удалось сохранить файл"));
                return;
            }
            final String safeName = cleanName(name, mime);
            final String type = (mime == null || mime.isEmpty()) ? guessMime(safeName) : mime;
            runOnUiThread(() -> saveFile(bytes, safeName, type));
        }

        @JavascriptInterface
        public void reload() {
            runOnUiThread(MainActivity.this::retry);
        }
    }

    private static String cleanName(String name, String mime) {
        String n = name == null ? "" : name.replaceAll("[\\\\/:*?\"<>|]", "_").trim();
        if (n.isEmpty()) {
            String ext = "bin";
            if (mime != null) {
                if (mime.contains("png")) ext = "png";
                else if (mime.contains("jpeg")) ext = "jpg";
                else if (mime.contains("pdf")) ext = "pdf";
                else if (mime.contains("csv")) ext = "csv";
                else if (mime.contains("excel") || mime.contains("sheet")) ext = "xls";
            }
            n = "karasu_" + System.currentTimeMillis() + "." + ext;
        }
        return n;
    }

    private static String guessMime(String name) {
        String lower = name.toLowerCase();
        if (lower.endsWith(".png")) return "image/png";
        if (lower.endsWith(".jpg") || lower.endsWith(".jpeg")) return "image/jpeg";
        if (lower.endsWith(".pdf")) return "application/pdf";
        if (lower.endsWith(".csv")) return "text/csv";
        if (lower.endsWith(".xls")) return "application/vnd.ms-excel";
        if (lower.endsWith(".xlsx")) return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";
        return "application/octet-stream";
    }

    private void saveFile(byte[] bytes, String name, String mime) {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            try {
                boolean image = mime.startsWith("image/");
                ContentValues values = new ContentValues();
                values.put(MediaStore.MediaColumns.DISPLAY_NAME, name);
                values.put(MediaStore.MediaColumns.MIME_TYPE, mime);
                values.put(MediaStore.MediaColumns.RELATIVE_PATH,
                        (image ? Environment.DIRECTORY_PICTURES : Environment.DIRECTORY_DOWNLOADS) + "/FK Karasu");
                Uri collection = image ? MediaStore.Images.Media.EXTERNAL_CONTENT_URI
                        : MediaStore.Downloads.EXTERNAL_CONTENT_URI;
                Uri uri = getContentResolver().insert(collection, values);
                if (uri == null) throw new IllegalStateException();
                try (OutputStream out = getContentResolver().openOutputStream(uri)) {
                    out.write(bytes);
                }
                toast(image ? "Сохранено в Галерею: " + name : "Сохранено в Загрузки: " + name);
                Intent open = new Intent(Intent.ACTION_VIEW).setDataAndType(uri, mime)
                        .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
                try { startActivity(open); } catch (ActivityNotFoundException ignored) { }
            } catch (Exception e) {
                toast("Не удалось сохранить файл");
            }
            return;
        }

        if (checkSelfPermission(Manifest.permission.WRITE_EXTERNAL_STORAGE) != PackageManager.PERMISSION_GRANTED) {
            pendingBytes = bytes;
            pendingName = name;
            pendingMime = mime;
            requestPermissions(new String[]{Manifest.permission.WRITE_EXTERNAL_STORAGE}, REQ_STORAGE);
            return;
        }
        try {
            File dir = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS);
            if (!dir.exists()) dir.mkdirs();
            File file = new File(dir, name);
            try (FileOutputStream out = new FileOutputStream(file)) {
                out.write(bytes);
            }
            DownloadManager dm = (DownloadManager) getSystemService(DOWNLOAD_SERVICE);
            dm.addCompletedDownload(name, name, true, mime, file.getAbsolutePath(), bytes.length, true);
            toast("Сохранено в Загрузки: " + name);
        } catch (Exception e) {
            toast("Не удалось сохранить файл");
        }
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] results) {
        if (requestCode != REQ_STORAGE || pendingBytes == null) return;
        byte[] bytes = pendingBytes;
        pendingBytes = null;
        if (results.length > 0 && results[0] == PackageManager.PERMISSION_GRANTED) {
            saveFile(bytes, pendingName, pendingMime);
        } else {
            toast("Нет доступа к памяти — файл не сохранён");
        }
    }

    private void toast(String text) {
        Toast.makeText(this, text, Toast.LENGTH_LONG).show();
    }

    // Перехватываем <a download href="blob:..."> и отдаём файл приложению.
    private static final String DOWNLOAD_HOOK =
            "(function(){if(window.__fkHook)return;window.__fkHook=1;"
            + "window.__fkSaveUrl=function(href,name,type){fetch(href).then(function(r){return r.blob();})"
            + ".then(function(b){var fr=new FileReader();fr.onloadend=function(){var s=String(fr.result);"
            + "FKKarasuApp.saveBase64(s.substring(s.indexOf(',')+1),name||'',type||b.type||'');};fr.readAsDataURL(b);})"
            + ".catch(function(){alert('Не удалось сохранить файл');});};"
            + "function grab(a){var h=a.getAttribute('href')||'';if(a.hasAttribute('download')&&(h.indexOf('blob:')===0||h.indexOf('data:')===0)){"
            + "window.__fkSaveUrl(a.href,a.getAttribute('download'),'');return true;}return false;}"
            + "var click=HTMLAnchorElement.prototype.click;HTMLAnchorElement.prototype.click=function(){if(!grab(this))return click.apply(this,arguments);};"
            + "document.addEventListener('click',function(e){var a=e.target&&e.target.closest&&e.target.closest('a[download]');"
            + "if(a&&grab(a)){e.preventDefault();e.stopPropagation();}},true);})();";

    // Google не пускает вход через встроенный браузер приложения — прячем эту кнопку.
    private static final String APP_CSS =
            "(function(){if(document.getElementById('fkAppCss'))return;var st=document.createElement('style');st.id='fkAppCss';"
            + "st.textContent='.google-login-btn,.login-divider{display:none!important}';"
            + "(document.head||document.documentElement).appendChild(st);})();";

    private static final String OFFLINE_PAGE =
            "<!doctype html><html><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>"
            + "<style>body{margin:0;min-height:100vh;display:flex;align-items:center;justify-content:center;"
            + "background:#F4F1EE;font-family:sans-serif;color:#25282d;text-align:center;padding:24px;box-sizing:border-box}"
            + "h1{font-size:20px;margin:0 0 8px}p{color:#7a808a;font-size:15px;margin:0 0 24px;line-height:1.4}"
            + "button{border:0;border-radius:12px;background:#FF8A00;color:#fff;font-size:16px;font-weight:600;padding:14px 28px}</style>"
            + "</head><body><div><h1>Нет связи с karasu.uz</h1>"
            + "<p>Проверьте интернет (Wi‑Fi или мобильные данные) и попробуйте снова.</p>"
            + "<button onclick='FKKarasuApp.reload()'>Повторить</button></div></body></html>";
}
