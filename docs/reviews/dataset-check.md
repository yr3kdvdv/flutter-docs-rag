# Независимая проверка flutter-qa-v1 — этап 05b

**26 ноября 2026, Europe/Chisinau. Проверяющий — Codex (GPT-6).** Автор набора — Claude Code, субагент evaluation-engineer. Репозиторий `yr3kdvdv/flutter-docs-rag`, ветка `stage-05-full-pipeline`, проверенный коммит `af6ab747e36fb6a295adb48ff01ea77eb1f749c3`. Проверка выполнена в отдельном чистом worktree с detached HEAD. Корпус [flutter/website@4fee025](https://github.com/flutter/website/tree/4fee0255ef9f0c85f6dd37513bf659613f57e5eb/sites/docs/src/content), конфигурация `lab1/configs/full.yaml`. Проверены обе части `flutter-qa-v1` в рамках аудита разметки.

**Решение — принять после исправлений. Из 45 вопросов 16 получили `ok`, 29 — `fix`, 0 — `drop`.** На `dev` — 6 / 9 / 0, на `test` — 10 / 20 / 0. Приоритет до принятия — убрать подсказки из формулировок, обеспечить два необходимых источника там, где стоит `multi_doc`, и согласовать четыре эталона с проверкой `expected_code`.

## Как проверялось

- Для каждого вопроса сверены смысл, тип, язык, эталон, проверяемые поля и секции. Секции извлечены тем же очистителем и парсером заголовков, что использует пайплайн. Дополнительно прочитаны соседние секции и альтернативные страницы, когда они могли полностью ответить на вопрос или изменить оценку.
- Пары `dev` и `test` сопоставлены по запрашиваемому факту и намерению. Отдельно сверены восемь пар с общей размеченной страницей и случаи, где вопрос повторяет заголовок, диагностическую строку или код.
- Для девяти вопросов `unanswerable` выполнен дополнительный поиск по заголовкам и очищенным текстам всех 647 страниц. Использованы варианты написания, технические синонимы и имена API. Просмотрены ближайшие по смыслу документы.
- Поля `must_include` и `expected_code` сравнены с эталонами функциями из `lab1/src/flutter_rag/evaluation/metrics.py:132` и `:141`. Первая ищет подстроки без учёта регистра. Вторая удаляет пробельные символы и ищет подстроку. Отдельно проверено присутствие обязательных маркеров в самом вопросе.
- Сверены исходные blob SHA-1 всех 717 уникальных файлов, на которые ссылается манифест, включая подключаемые фрагменты. После повторного ingest все 50 текущих `gold_sections` найдены среди `section_ids` точек Qdrant. Это подтверждает возможность их извлечения из индекса.

## Вопросы dev

Номера строк в таблицах относятся к [dev.jsonl](../../lab1/evaluation/datasets/flutter-qa-v1/dev.jsonl) и [test.jsonl](../../lab1/evaluation/datasets/flutter-qa-v1/test.jsonl) соответственно. Для всех строк язык и тип соответствуют контракту, кроме указанных замечаний о полноте `multi_doc` и границе `unanswerable`. Все предлагаемые изменения перечислены ниже таблиц.

| ID | Строка | Тип / язык | Статус | Причина и проверенное основание |
|---|---:|---|---|---|
| dev-001 | 1 | factoid / ru | ok | `deployment/obfuscate#limitations` прямо разделяет обфускацию Dart и минификацию release-сборки для web. Пустой `must_include` подходит для ответа с допустимыми русскими формулировками. |
| dev-002 | 2 | factoid / en | fix · P2 | `deployment/android#version-code-and-name` подтверждает эталон. Подстрока `version` содержится в `versionCode` и `versionName` из вопроса и не проверяет название поля. |
| dev-003 | 3 | factoid / ru | fix · P2 | `security/index#reporting-vulnerabilities` подтверждает форму, 5 рабочих дней и запасной контакт. Маркер `5` пропустит ответ с любым числом, содержащим эту цифру. |
| dev-004 | 4 | multi_doc / ru | ok | `testing/build-modes#debug` устанавливает ограничение hot reload, `tools/hot-reload#native-code` даёт способ применить изменение Kotlin. Оба факта нужны, чтобы объяснить ограничение режима и действие. |
| dev-005 | 5 | multi_doc / en | fix · P2 | Оба имени верны, но эталон указывает полный путь только для iOS. Для симметричного вопроса про адрес источники — Android `#assetlinks-json` и iOS `#create-and-host-apple-app-site-association-json-file`. Общая iOS-секция дублирует название файла. |
| dev-006 | 6 | multi_doc / ru | fix · P2 | `ephemeral-vs-app#app-state` классифицирует корзину. `simple#changenotifier` и `#changenotifierprovider` покрывают модель и размещение. Упомянутый в эталоне способ чтения находится в `simple#consumer`, которого нет в gold. |
| dev-007 | 7 | lookup / en | fix · P2 | Команда совпадает с примером macOS в `deployment/android#create-an-upload-keystore`. Вопрос почти повторяет заголовок. `expected_code` проверяет начало команды и пропускает отсутствие типа, размера, срока и алиаса. |
| dev-008 | 8 | lookup / ru | fix · P2 | Таблица в `platform-integration/web/wasm#serve-the-built-output-with-an-http-server` подтверждает оба заголовка. Детерминированная проверка допускает ответ с любым значением COEP. |
| dev-009 | 9 | lookup / en | fix · P2 | `deployment/flavors#use-flavors-in-flutter-code` и `#access-the-current-flavor` подходят для Android. Исходный вопрос допускает другие платформы, где отличается обработка значения по умолчанию. Эталон называет пакет, но проваливает проверку строки импорта. |
| dev-010 | 10 | contextual / ru | fix · P1 | Строка из вопроса дословно совпадает с заголовком `testing/common-errors#vertical-viewport-was-given-unbounded-height`. Исходник допускает несколько вариантов ограничения высоты, а маркер засчитывает только `Expanded`. |
| dev-011 | 11 | contextual / en | fix · P2 | `app-architecture/guide#repositories` допускает композицию в view model или domain layer. Исходный вопрос не просит оба места, а `must_include` отклоняет корректный ответ, предлагающий domain layer. |
| dev-012 | 12 | contextual / en | ok | `tools/hot-reload#recent-code-change-is-included-but-app-state-is-excluded` подтверждает сохранение значения уже инициализированного статического поля. Эталон объясняет симптом и называет hot restart. |
| dev-013 | 13 | unanswerable / ru | ok | В сценариях встраивания и перечне платформ есть общие сведения. Инструкций по HarmonyOS NEXT или AppGallery в снимке не найдено. |
| dev-014 | 14 | unanswerable / en | ok | Сверены варианты написания GetX и обзор способов управления состоянием. Инструкции для GetxController и Obx отсутствуют. |
| dev-015 | 15 | unanswerable / ru | ok | Разделы анимаций покрывают встроенные инструменты Flutter. Импорт Lottie, After Effects и Bodymovin в снимке не описан. |

## Вопросы test

| ID | Строка | Тип / язык | Статус | Причина и проверенное основание |
|---|---:|---|---|---|
| test-001 | 1 | factoid / en | fix · P2 | `testing/build-modes#profile` подтверждает отказ от эмуляторов и симуляторов для измерения. Единственный маркер `profile` уже дан в вопросе и ничего не говорит о подходящем устройстве. |
| test-002 | 2 | factoid / ru | fix · P2 | `perf/impeller#ios` подтверждает невозможность переключения. Оба маркера даны в вопросе и могут присутствовать в противоположном по смыслу ответе. |
| test-003 | 3 | factoid / ru | fix · P2 | `add-to-app/multiple-flutters#scenarios` даёт около 180 kB на дополнительный экземпляр. Обоснование про общий `FlutterEngineGroup` находится в `#components`. Маркер `180` не проверяет единицу или порядок величины. |
| test-004 | 4 | factoid / en | ok | `platform-integration/web/wasm#switch-to-the-latest-version-of-flutter` даёт минимум 3.24. Версия отсутствует в вопросе и подходит для буквальной проверки. |
| test-005 | 5 | factoid / en | fix · P2 | Вступление страницы `packages-and-plugins/swift-package-manager/for-app-developers#` покрывает версию, режим сопровождения и полную дату. `#how-to-turn-on-swift-package-manager` повторяет только часть. Маркер `2026` пропускает неверные день и месяц. |
| test-006 | 6 | factoid / ru | fix · P1 | Вопрос перечисляет три уровня в том же порядке, который и требуется назвать. Вступление `cookbook/design/themes#` верно задаёт приоритет, но исходная формулировка отдаёт эталон без поиска. |
| test-007 | 7 | multi_doc / en | fix · P1 | `perf/isolates#web-platforms-and-compute` отвечает на текущее сравнение самостоятельно. Оба маркера уже в вопросе. Чтобы требовался cookbook, нужно спросить про конкретный пример и вызов из него. |
| test-008 | 8 | multi_doc / en | ok | `cookbook/persistence/key-value#supported-types` перечисляет типы. `data-and-backend/persistence/choose-a-database#use-sqlite-or-key-value-storage-locally` подтверждает отсутствие автоматической синхронизации. `List<String>` — полезный частичный маркер. Полноту списка и факт синхронизации оценивает judge. |
| test-009 | 9 | multi_doc / en | fix · P2 | `android-predictive-back#background` объясняет несовместимость, но размеченный `#popscope` не показывает, как сохранить диалог. Пример миграции и manifest действительно нужны для полного ответа на уточнённый вопрос. |
| test-010 | 10 | multi_doc / ru | fix · P2 | `deployment/flavors#overview` и `deployment/flavors-ios#overview` поддерживают сравнение. Для проверки двух сторон одного `Xcode` мало. Android-термин `product flavor` есть в эталоне и gold-секции. |
| test-011 | 11 | multi_doc / ru | ok | `deployment/obfuscate#obfuscate-your-app` содержит оба флага, `deployment/android#build-an-app-bundle` — цель сборки и путь файла. Ответ соединяет факты двух страниц. |
| test-012 | 12 | multi_doc / ru | fix · P2 | `ui-design-and-styling#tap-target-size` называет платформенные единицы, `accessibility-testing#testing-accessibility-on-mobile` содержит обе проверки. В примере теста уже указаны оба числа. Явный запрос единиц делает первую страницу необходимой. `must_include` пропускает iOS-проверку. |
| test-013 | 13 | lookup / en | fix · P2 | `perf/impeller#android` подтверждает метаданные. Проверка имени XML-атрибута проходит даже при `android:value="true"`. |
| test-014 | 14 | lookup / en | fix · P2 | В `ui/internationalization/index#add-your-own-localized-messages` приведён конкретный пример. Исходный вопрос не фиксирует, нужны ли именно его имена файлов или общий шаблон. Проверяется код только первой настройки из трёх. |
| test-015 | 15 | lookup / en | fix · P2 | Команда совпадает с `testing/integration-tests/index#add-the-integration_test-dependency`. Вопрос повторяет название пакета и почти повторяет заголовок. Поле `expected_code` уже проверяет команду. |
| test-016 | 16 | lookup / ru | fix · P2 | `tools/widget-previewer#preview-a-widget` подтверждает аннотацию и импорт. Эталон даёт путь в прозе и проваливает проверку строки импорта. |
| test-017 | 17 | lookup / ru | ok | `packages-and-plugins/swift-package-manager/for-app-developers#turn-off-swiftpm-for-a-single-project` подтверждает область действия и вложенность настройки. Значение `false` проверяется кодом. |
| test-018 | 18 | lookup / ru | fix · P2 | `ui/navigation/url-strategies#configuring-the-url-strategy` подтверждает зависимость и порядок вызовов. Эталон не содержит точное `usePathUrlStrategy();` и проваливает `expected_code`. |
| test-019 | 19 | contextual / en | fix · P1 | Из `deployment/obfuscate#caveat` в вопрос перенесён практически дословный вызов с тем же `foo` и `'Foo'`. Маркер `obfusc` уже содержится в вопросе и не проверяет объяснение. |
| test-020 | 20 | contextual / ru | fix · P2 | `perf/isolates#limitations-of-isolates` подтверждает раздельную память. Вопрос воспроизводит уникальное имя `configuration` и опыт из этого раздела. Часть про отправку сообщения в эталоне выходит за рамки исходного запроса. |
| test-021 | 21 | contextual / ru | fix · P2 | `cookbook/navigation/set-up-app-links#2-modify-androidmanifest-xml` даёт исправление. Причину после обновления явно объясняет `release/breaking-changes/deep-links-flag-change`. Эталон пропускает смену значения по умолчанию и не содержит XML, который проверяет `expected_code`. |
| test-022 | 22 | contextual / ru | fix · P2 | `ui/internationalization/index#localizing-for-ios-updating-the-ios-app-bundle` подтверждает шаги. Один маркер `Xcode` пропускает ответ без указания проекта и раздела настройки. |
| test-023 | 23 | contextual / en | ok | `ui/navigation/url-strategies#configuring-your-web-server` объясняет 404, fallback локального сервера и rewrite на `index.html`. Отдельная конфигурация nginx не требуется формулировкой. |
| test-024 | 24 | contextual / en | fix · P2 | `tools/widget-previewer#restrictions-and-limitations` объясняет ограничение платформы и поведение при вызове. `dart:io` уже в вопросе. Подстрока `web` срабатывает и в ответе без названия среды превью. |
| test-025 | 25 | unanswerable / en | ok | Платформенные каналы дают общий способ обращения к нативному API. Чтение NFC/NDEF на Android и iOS в корпусе не описано. |
| test-026 | 26 | unanswerable / ru | ok | HTTPS, сертификаты подписи и TLS dev-сервера встречаются. Проверки сертификата или открытого ключа в HTTP-клиенте Flutter по заданному сценарию не найдено. |
| test-027 | 27 | unanswerable / en | fix · P1 | Вопрос содержит две части. Перечень поддерживаемых платформ даёт основание для ответа про официальную поддержку, а общие материалы про адаптивную вёрстку — для части ответа об интерфейсе. Инструкций по сборке и обработке круглого экрана именно на Wear OS нет. Лучше попросить этот конкретный процесс. |
| test-028 | 28 | unanswerable / ru | ok | Корпус содержит материалы о Firebase. Настройка Supabase Auth, GoTrue и соответствующего Flutter-пакета отсутствует. |
| test-029 | 29 | unanswerable / en | ok | Проверены WebRTC, имена браузерных API и P2P-термины. Общие сетевые рецепты не дают способа реализовать видеозвонок. |
| test-030 | 30 | unanswerable / ru | ok | WebSocket-рецепт и примеры IoT не дают подключения к MQTT-брокеру. Проверены имена клиентов, брокеров и полное название протокола. |

## Предлагаемые изменения полей

Остальные поля по каждой строке сохраняют текущие значения. Для новых `gold_sections` берутся дословные `supporting_excerpts` из названных секций того же снимка. Для удалённых секций убираются соответствующие цитаты. Указанные ниже строки кода можно включить в `expected_answer`, чтобы эталон проходил `expected_code`. При пустом `must_include` правильность факта оценивается по смыслу.

### Dev

- **dev-002.** `must_include` → `["pubspec.yaml"]`. Проверку поля `version` оставить для оценки содержания эталона.
- **dev-003.** `must_include` → `["g.co/vulnz"]`. Эталон сохраняет условие про пять рабочих дней. Оценивать срок по смыслу с учётом числа, единицы и того, что дни рабочие.
- **dev-005.** `question` → “For an HTTPS link on my own domain to open the installed Flutter app on Android and on iOS, what exact association URL must I serve on each platform?” `expected_answer` → “Serve `https://<domain>/.well-known/assetlinks.json` for Android and `https://<domain>/.well-known/apple-app-site-association` for iOS. The iOS filename has no `.json` extension.” `must_include` → `[".well-known/assetlinks.json", ".well-known/apple-app-site-association"]`. `gold_sections` → `["cookbook/navigation/set-up-app-links#assetlinks-json", "cookbook/navigation/set-up-universal-links#create-and-host-apple-app-site-association-json-file"]`. В новых цитатах оставить обе строки с URL из этих секций.
- **dev-006.** Добавить в `gold_sections` `data-and-backend/state-mgmt/simple#consumer`, в `supporting_excerpts` — фрагмент с `Consumer<CartModel>` из этого раздела. `must_include` → `["ChangeNotifier", "notifyListeners", "ChangeNotifierProvider", "Consumer"]`.
- **dev-007.** `question` → “Play Console asks for an upload key. On my Mac with the JDK installed, which terminal command generates the signing file with the name, alias and settings from the Flutter guide?” `expected_code` → `keytool -genkey -v -keystore ~/upload-keystore.jks -keyalg RSA -storetype JKS -keysize 2048 -validity 10000 -alias upload`. Сохранить команду в одну строку в эталоне. Для корректных ответов с другим порядком аргументов учитывать эквивалентность при смысловой оценке.
- **dev-008.** `question` → «Какие два HTTP-заголовка должен отдавать сервер, чтобы Flutter web, собранный в WebAssembly, мог рендерить в несколько потоков? Перечисли допустимые значения каждого». `must_include` → `["Cross-Origin-Embedder-Policy", "credentialless", "require-corp", "Cross-Origin-Opener-Policy", "same-origin"]`. В эталоне сохранить, что два значения COEP альтернативны.
- **dev-009.** `question` → “Our Android Flutter app points to a different API in staging. Which Dart constant tells me which build flavor was selected, and how do I import it?” `expected_answer` → “Read `appFlavor`. It contains the name selected with `--flavor`, such as `staging`. Add `import 'package:flutter/services.dart';`.” `expected_code` остаётся строкой импорта.
- **dev-010.** `question` → «В `Column` сначала идёт заголовок, под ним `ListView`. При построении экрана Flutter не может определить высоту списка. Почему так происходит и какой виджет из документации позволит списку занять всё оставшееся место?» `expected_answer` → «`Column` по умолчанию не даёт обычному дочернему `ListView` конечного ограничения по высоте. Список пытается занять всю доступную высоту. Оберни его в `Expanded`, чтобы ограничить его высотой, оставшейся после заголовка». Сохранить `must_include` `["Expanded"]`.
- **dev-011.** `question` → “An orders screen needs data from both OrdersRepository and UserRepository. Should one repository call the other? Name both places Flutter's architecture guide allows for combining their data.” `must_include` → `["view model", "domain layer"]`. Существующий эталон перечисляет оба места.

### Test

- **test-001.** `must_include` → `[]`. В оценке ответа проверять физическое устройство и причину, по которой эмулятор или симулятор не даёт показательных измерений.
- **test-002.** `must_include` → `[]`. В смысловой оценке проверять, что на iOS отсутствует переключение на Skia.
- **test-003.** `question` → «Какой примерный дополнительный расход памяти приводит документация Flutter для каждого следующего экземпляра движка при встраивании нескольких Flutter-экранов через `FlutterEngineGroup`?» `expected_answer` → «Около 180 кБ на каждый дополнительный экземпляр Flutter». `must_include` → `[]`. Смысловая оценка принимает эквивалентную запись единицы. `#scenarios` достаточно для величины, которую спрашивает новая формулировка.
- **test-005.** `gold_sections` → `["packages-and-plugins/swift-package-manager/for-app-developers#"]`. `must_include` → `["3.44", "read-only"]`. Дату оценивать целиком по смыслу, не фиксируя один формат записи.
- **test-006.** `question` → «В Material-приложении один параметр цвета задан и в настройках компонента, и в двух темах. В каком порядке Flutter разрешает конфликт между темой приложения, стилем виджета и ближайшей локальной темой?» Эталон и `gold_sections` остаются прежними.
- **test-007.** `question` → “In Flutter's photo-list cookbook recipe, what exact call dispatches the JSON-to-photo conversion? Explain how that helper compares with `Isolate.run()` on mobile and desktop and where its callback executes on the web.” `expected_answer` → “The recipe uses `return compute(parsePhotos, response.body);`. On mobile and desktop, `await compute(fun, message)` is equivalent to `await Isolate.run(() => fun(message))`. On the web, `compute()` still compiles and runs its callback on the main thread.” `must_include` → `["compute", "parsePhotos"]`. `expected_code` → `compute(parsePhotos, response.body)`. Обе текущие gold-секции теперь нужны.
- **test-009.** `question` → “I need to keep the discard-changes dialog when moving my Flutter screen away from `WillPopScope`. Why does Android predictive back require an earlier decision, how do I preserve the confirmation in Dart, and what manifest setting enables the gesture?” `expected_answer` → “The animation starts as the gesture begins, so pop eligibility must be known in advance. Use `PopScope(canPop: false, …)` to block an immediate pop when confirmation is needed. In `onPopInvokedWithResult`, return if `didPop` is true, otherwise show the dialog and pop explicitly if the user confirms. Add `android:enableOnBackInvokedCallback="true"` to `<application>` in `AndroidManifest.xml`.” `must_include` → `["PopScope", "canPop", "onPopInvokedWithResult", "enableOnBackInvokedCallback"]`. В `gold_sections` заменить `release/breaking-changes/android-predictive-back#popscope` на `release/breaking-changes/android-predictive-back#migrating-a-back-confirmation-dialog`. Сохранить `#background` и Android-секцию про манифест. Цитату для новой секции взять из примера миграции диалога.
- **test-010.** `must_include` → `["product flavor", "Xcode"]`. Сопоставление product flavor и схемы по-прежнему проверять по смыслу.
- **test-012.** `question` → «Какой минимальный размер области нажатия рекомендуют Android и iOS, в каких единицах он указан для каждой платформы и какими проверками Accessibility Guideline API протестировать оба размера в widget-тесте?» `must_include` → `["meetsGuideline", "androidTapTargetGuideline", "iOSTapTargetGuideline"]`. Эталон сохраняет 48×48 dp и 44×44 pt. Размеры с единицами проверяются по смыслу.
- **test-013.** `expected_answer` → “Under `<application>` in `AndroidManifest.xml`, add `<meta-data android:name="io.flutter.embedding.android.EnableImpeller" android:value="false" />`.” `expected_code` → `android:value="false"`. Сохранить имя метаданных в `must_include`. Его положение и привязку значения к этому элементу оценивать по смыслу.
- **test-014.** `question` → “Using the file names and directory from Flutter's English/Spanish localization example, show the complete three-line `l10n.yaml` for the ARB input and generated Dart file.” `expected_answer` и `expected_code` → приведённый ниже YAML. `generate: true` в другом файле допустим как пояснение.
- **test-015.** `question` → “I want to run end-to-end tests on a device using the package shipped with the Flutter SDK. What terminal command adds that package under dev dependencies?” `must_include` → `[]`. Полную команду уже проверяет `expected_code`.
- **test-016.** `expected_answer` → «Добавь `import 'package:flutter/widget_previews.dart';` и поставь `@Preview` над функцией верхнего уровня, возвращающей `Widget` или `WidgetBuilder`. Например, `@Preview(name: 'My Sample Text')`». Сохранить текущий `expected_code`.
- **test-018.** `expected_answer` → «Добавь `flutter_web_plugins` в `pubspec.yaml` как зависимость Flutter SDK. Импортируй `package:flutter_web_plugins/url_strategy.dart` и вызови `usePathUrlStrategy();` перед `runApp`». Сохранить текущий `expected_code`.
- **test-019.** `question` → “Our debug tests identify a Dart object by comparing its type name to a stored string. The assertion starts failing only after we enable name obfuscation in the release build. Why?” `expected_answer` → “Obfuscation can rename Dart classes. A runtime type name in the obfuscated binary can differ from the original class name, so the string comparison is no longer reliable.” `must_include` → `[]`. `deployment/obfuscate#caveat` остаётся достаточным.
- **test-020.** `question` → «В фоне пересчитался лимит хранения истории. Я записал его в глобальное поле из отдельного изолята, но UI всё ещё видит старый лимит. Почему так происходит и как сообщить главному изоляту новое значение?» `expected_answer` → «У каждого изолята своя память и свои глобальные поля. Запись в поле фонового изолята не меняет поле главного. Передай новый лимит сообщением и обнови состояние в главном изоляте». `perf/isolates#limitations-of-isolates` подтверждает разделение полей и обмен сообщениями.
- **test-021.** `question` → «После обновления Flutter мой Android-плагин `app_links` перестал получать диплинки. Что изменилось в поведении Flutter по умолчанию, в каком стабильном релизе и как вернуть обработку плагину?» `expected_answer` → «Во Flutter 3.27 встроенная обработка диплинков стала включаться по умолчанию и может мешать `app_links`. В `AndroidManifest.xml` внутри `<activity>` добавь `<meta-data android:name="flutter_deeplinking_enabled" android:value="false" />`». `gold_documents` → `["release/breaking-changes/deep-links-flag-change"]`. `gold_sections` → `["release/breaking-changes/deep-links-flag-change#summary", "release/breaking-changes/deep-links-flag-change#migration-guide", "release/breaking-changes/deep-links-flag-change#timeline"]`. В цитатах отразить смену `false` на `true`, XML и стабильную версию. `must_include` → `["3.27", "flutter_deeplinking_enabled"]`. Текущий `expected_code` сохраняется и проверяет `false`.
- **test-022.** `must_include` → `["ios/Runner.xcodeproj", "Localizations"]`. Текущий эталон включает оба маркера и необходимые шаги.
- **test-024.** `question` → “A widget can read a local file in my Android app, but throws when it attempts the same read in Flutter Widget Previewer. What platform does the preview run on, and why is the file API unavailable there?” `must_include` → `["Flutter Web"]`. Существующий эталон объясняет недоступность нативного API.
- **test-027.** `question` → “What Wear OS-specific build and deployment steps does the Flutter documentation give for targeting a round smartwatch display?” Сохранить тип, отказ и пустые gold-поля. Этот вопрос требует инструкции по конкретной платформе.

Полный пример для `test-014`

```yaml
arb-dir: lib/l10n
template-arb-file: app_en.arb
output-localization-file: app_localizations.dart
```

### Цитаты для изменённой разметки

Текст каждой строки сверён с указанной секцией. `\n` обозначает перевод строки внутри значения `text`.

| ID | `section_id` | `text` |
|---|---|---|
| dev-005 | `cookbook/navigation/set-up-app-links#assetlinks-json` | `<webdomain>/.well-known/assetlinks.json` |
| dev-005 | `cookbook/navigation/set-up-universal-links#create-and-host-apple-app-site-association-json-file` | `<webdomain>/.well-known/apple-app-site-association` |
| dev-006 | `data-and-backend/state-mgmt/simple#consumer` | `Consumer<CartModel>` |
| test-009 | `release/breaking-changes/android-predictive-back#migrating-a-back-confirmation-dialog` | `canPop: false,` |
| test-009 | `release/breaking-changes/android-predictive-back#migrating-a-back-confirmation-dialog` | `if (shouldPop ?? false) {` |
| test-021 | `release/breaking-changes/deep-links-flag-change#summary` | `The default value for Flutter's deep linking option has changed from` + `\n` + `` `false` to `true` `` |
| test-021 | `release/breaking-changes/deep-links-flag-change#migration-guide` | `<meta-data android:name="flutter_deeplinking_enabled" android:value="false" />` |
| test-021 | `release/breaking-changes/deep-links-flag-change#timeline` | `Stable release: 3.27` |

## Отсутствие ответа в корпусе

Дополнительные запросы выполнены без учёта регистра по заголовкам и текстам **всех 647 документов**. Ни один из наборов ниже не нашёл соответствующей страницы. При чтении соседних тем также не нашлось полных ответов.

| ID | Дополнительные варианты поиска | Что есть в ближайших материалах |
|---|---|---|
| dev-013 | Harmony OS, App Gallery, ArkTS, OHPM, OHOS | `embedded/index` обсуждает перенос на новые системы в общем виде. |
| dev-014 | JonatasLaw, get_cli, GetXController, Obx | `state-mgmt/options` описывает другие варианты управления состоянием. |
| dev-015 | After-Effects, Bodymovin, Lottie, Airbnb рядом с animation | `ui/animations/index` знакомит со штатными способами анимации. |
| test-025 | NDEF, RFID, ISO 14443, near-field communication | `platform-integration/platform-channels` описывает мост к платформенным API. |
| test-026 | SPKI, public-key pinning, SecurityContext, badCertificateCallback | `platform-integration/web/web-dev-config-file` относится к TLS dev-сервера. Сертификаты в разделе Windows относятся к подписи приложения. |
| test-027 | WearOS, smart watch, wearable, WatchOS, round screen/display, wrist | `reference/supported-platforms` перечисляет платформы и даёт частичный ответ на исходный вопрос о поддержке. `learn/pathway/tutorial/adaptive-layout` покрывает общую адаптацию интерфейса. |
| test-028 | GoTrue, PostgREST, supabase_flutter, Supabase Auth | `data-and-backend/firebase` описывает другой сервис. |
| test-029 | RTCPeerConnection, getUserMedia, peer-to-peer, STUN/TURN server | `cookbook/networking/web-sockets` покрывает двустороннее соединение с сервером. |
| test-030 | mqtt_client, Mosquitto, PubSubClient, topic subscription, Message Queuing Telemetry Transport | Сетевые рецепты покрывают HTTP и WebSocket. `packages-and-plugins/developing-packages` упоминает IoT как пример платформы для плагина. |

Критерий отказа ограничен зафиксированным снимком. Для `test-027` предложение выше сохраняет проверку отказа и устраняет возможность полного ответа на один из двух исходных подвопросов.

## Лексическая близость и разделение dev/test

- Самые сильные подсказки — название ошибки в `dev-010`, уже заданный порядок в `test-006` и скопированное выражение из примера в `test-019`. `dev-007` и `test-015` близки к своим заголовкам. В `test-020` конкретное имя переменной повторяет пример. Для всех шести даны новые формулировки.
- У `dev-006` пример с корзиной взят из документации намеренно, поскольку требуется конкретный подход из примера. У `dev-008`, `test-004` и `test-024` имя платформы, технологии или инструмента задаёт предмет вопроса. Это естественные поисковые ориентиры. Факт или решение по-прежнему нужно найти.
- В восьми исходных вопросах хотя бы один `must_include` находится внутри текста вопроса. Полностью копируются наборы маркеров в `test-001`, `test-002`, `test-007`, `test-015` и `test-019`. Например, проверка `PopScope` в `test-009` срабатывает на подстроке `WillPopScope`. Предложенные маркеры разделяют наличие технического термина и смысл ответа. `Hit@1 = 11/12` в исходном Gemini-прогоне на dev согласуется с риском лёгких вопросов. Из аудита разметки нельзя оценить величину эффекта. [Прогон этапа 05](../evidence/stage05/README.md)
- Смысловых дублей между `dev` и `test` не нашёл. Есть восемь пар с общей gold-страницей и **ноль** пар с общей gold-секцией. Наибольшая тематическая близость у `dev-001` и `test-019` об obfuscation, у `dev-004` и `test-001` о режимах сборки, а также у `dev-005` и `test-021` о диплинках. Они спрашивают разные факты. Для `test-021` предложена отдельная страница миграции.
- Остальные пары с общей страницей — `dev-001` / `test-011` (web-ограничение / Android-сборка), `dev-002` / `test-011` (версия / путь bundle), `dev-007` / `test-011` (ключ / путь bundle), `dev-008` / `test-004` (HTTP-заголовки / версия SDK) и `dev-009` / `test-010` (чтение текущего flavor / устройство конфигураций на двух платформах).
- В каждом из пяти типов 3 dev и 6 test. Всего 23 вопроса на русском и 22 на английском. Перекос по языку внутри типа не превышает одного вопроса. Пересчитано **30 уникальных gold-документов**. В [README набора](../../lab1/evaluation/datasets/flutter-qa-v1/README.md) указано 34. Исправить число при обновлении разметки. Разделение на 15 dev и 30 test и все пять типов сохраняются предложенными правками.

## Воспроизведение и вывод dataset-check

1. Чистая среда Python 3.12.15. Первый `uv sync --locked` остановился из-за DNS для PyPI в sandbox, exit 2. После копирования локального кэша в изолированную папку `uv sync --locked --offline` завершился с exit 0, установлен 91 пакет вместе с приложением. `uv run pytest -o addopts= -q` → **151 passed**, exit 0. `uv run ruff check .` и `uv run ruff format --check .` → exit 0, 60 файлов уже отформатированы.
2. В отдельный `DATA_DIR` скопированы ранее полученные манифесты, raw-блобы, кэш и индекс. Для повторного ingest использованы `pipeline.ingest`, обычный публичный `GitHubClient`, `configs/full.yaml` и копия embedded Qdrant. Провайдер embeddings в проверочном запуске останавливал обработку при попытке внешнего запроса. Langfuse отключён для этого прогона. Повтор завершился с exit 0. Два запроса к GitHub сверили pinned commit и его дерево. Получено 647 неизменившихся страниц, 19 skipped, 0 failed, 0 загрузок, 0 upserts, 0 запросов embeddings и 5 815 точек.
3. После ingest из `lab1/` запущена команда `DATA_DIR=<изолированный каталог>/data uv run flutter-rag dataset-check` в созданной среде. Exit 0. Фактический вывод ниже.

```text
dataset: flutter-qa-v1  corpus: 4fee0255ef9f0c85f6dd37513bf659613f57e5eb
dev.jsonl sha256 04b5fe8c66ad5a977bd34462cb521776774f8f551ff1d8227bda4f8a988e62ca
test.jsonl sha256 14f6c63353b6556a1a2032eaf13de794e1796040d343005d4b8359db92fdecd4
type          split  ru  en
factoid       dev     2   1
multi_doc     dev     2   1
lookup        dev     1   2
contextual    dev     1   2
unanswerable  dev     2   1
factoid       test    3   3
multi_doc     test    3   3
lookup        test    3   3
contextual    test    3   3
unanswerable  test    3   3
checked: 80 excerpts, 50 gold sections, 30 absent terms; statuses {'draft': 45}
OK
```

Сверка отчёта подтвердила 45 уникальных ID, предложения по всем 29 строкам `fix` и восемь новых дословных цитат в нужных секциях. Предлагаемые эталоны и маркеры проверены в памяти функциями `must_include_found` и `code_present`.

В рамках 05b проверена разметка текущей версии. Прогоны `evaluate`, запросы к LLM и оценка качества новых формулировок через поиск относятся к следующим этапам. Единственный новый файл по `git status` — этот отчёт. После исправлений интегратору нужно повторить `dataset-check`, сверить новые цитаты и маркеры, затем зафиксировать принятую версию набора до подбора параметров на `dev`.
