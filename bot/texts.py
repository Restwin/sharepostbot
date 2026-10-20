"""All user-facing phrases and texts of the bot in one place.

Handlers and menus reference these constants; sections map to domains
(common, access, wizard, ...).

Conventions:
- strings with substitutions use `str.format()` with named placeholders, e.g.
  `"...{name}..."`; HTML-escape substituted values at the call site
  (`html_escape(...)`), not here
- `docs/TEXTS.md` is generated from this module, so update or regenerate it
  when a string changes
"""

from __future__ import annotations

# ────────────────────────────────────────────────────────────────────────────
# Common — приветствие, меню, /help, /recheck, catch-all
# ────────────────────────────────────────────────────────────────────────────

START_GREETING = (
    "Привет, <b>{name}</b>! 👋\n\n"
    "Я публикую посты в канал сообщества. Нажми «📝 Создать пост» в меню, "
    "чтобы начать, или посмотри все команды: /help"
)

RECHECK_OK = "Доступ подтверждён ✅"

MENU_TITLE = "📋 Меню:"

MENU_UNAVAILABLE = "Меню недоступно."

MENU_UNAVAILABLE_COMMANDS = (
    "Меню недоступно. Доступные команды: "
    "<code>/whyblocked</code>, <code>/contacts</code>, <code>/recheck</code>."
)

PM_FALLBACK = (
    "Я публикую посты в канал сообщества.\n"
    "Напиши /post, чтобы создать пост, или /help — список команд."
)

CB_CANT_EDIT = "Не могу отредактировать сообщение."

CB_LINK_MISSING = "Ссылка не заполнена."

CB_ADMIN_ONLY = "Только для админов."

CB_UNKNOWN_LINK = "Неизвестная ссылка."

MY_CHATS_EMPTY = "🔗 Ты ещё не добавил ни одного чата. Используй <code>/add_chat</code>."

ALL_CHATS_EMPTY = "🔗 Список чатов пуст."

MY_CHATS_TITLE = "🔗 <b>Добавленные чаты:</b>"

ALL_CHATS_TITLE = "🔗 <b>Все чаты:</b>"

CHAT_ROW = "🔗 {name} <code>id: {chat_id}</code> <i>(без ссылки)</i>"

CHAT_ROW_LINK = '🔗 <a href="{link}">{name}</a> <code>id: {chat_id}</code>'

CHAT_ROW_BLOCKED_PREFIX = "🚫 "

VERSION_REPLY = "Версия: <code>{version}</code>"

# ────────────────────────────────────────────────────────────────────────────
# Access — гость, заблокированный, /whyblocked, контакты
# ────────────────────────────────────────────────────────────────────────────

ROLE_LABEL_STAFF = "админ"
ROLE_LABEL_ALLOW = "пользователь с доступом"
ROLE_LABEL_BLOCKED = "доступ ограничен"
ROLE_LABEL_UNKNOWN = "пользователь"
ROLE_LABEL_OTHER = "неизвестно"

CONTACTS_EMPTY = "Список админов пока пуст. Обратитесь позже."
CONTACTS_HEADER = "<b>Админы сообщества:</b>\n\n"

REASON_UNSPECIFIED = "причина не указана"

GUEST_MESSAGE = (
    "Публикация постов недоступна: вы не состоите в канале сообщества.\n\n"
    "Этот бот принадлежит закрытому сообществу и публикует посты только "
    "для его участников. Вступите в канал сообщества, чтобы публиковать посты.\n\n"
    "{contacts}\n\n"
    "Перепроверить доступ: /recheck"
)

BLOCKED_MENTION_REPLY = (
    "Извините, вам недоступна публикация через упоминание в чате.\n\n"
    "<b>Причина:</b> {reason}\n\n"
    "Подробности — в ЛС у бота командой <code>/whyblocked</code>."
)

NOT_MEMBER_MENTION_REPLY = (
    "Публикация недоступна: вы не состоите в канале сообщества.\n"
    "Вступите в канал, затем перепроверьте доступ в ЛС: <code>/recheck</code>."
)

BLOCKED_PM_REPLY = (
    "Вам недоступна публикация постов через ЛС.\n\n"
    "<b>Причина:</b> {reason}\n\n"
    "Полные детали — командой <code>/whyblocked</code>. "
    "Связаться с админами — <code>/contacts</code>."
)

WHYBLOCKED_STATUS = "<b>Ваш статус:</b> {role}"
WHYBLOCKED_REASON = "<b>Причина блокировки:</b> {reason}"
WHYBLOCKED_WHERE = "<b>Где ограничено:</b> {mode}"
WHYBLOCKED_BY = "<b>Заблокировал:</b> {name}"
WHYBLOCKED_NO_RESTRICTIONS = "Ограничений нет — можете публиковать посты."
WHYBLOCKED_NOT_MEMBER = (
    "Однако вы не состоите в канале сообщества — вступите, чтобы публиковать посты."
)
WHYBLOCKED_CONTACT_HINT = "\nПо вопросам доступа пишите админам: <code>/contacts</code>"
WHYBLOCKED_CONTACTS_HINT = "\n\nСписок админов: /contacts"

RESTRICT_MODE_LABEL = {
    "0": "только ЛС",
    "1": "только упоминания в чате",
    "2": "везде (ЛС и упоминания)",
}
RESTRICT_MODE_UNKNOWN = "—"

BLOCKED_CHAT_REASON_LINE = "<b>Причина блокировки:</b> {reason}"
BLOCKED_CHAT_BY_LINE = "<b>Заблокировал:</b> {name}"

# ────────────────────────────────────────────────────────────────────────────
# Onboarding — добавление бота в чат
# ────────────────────────────────────────────────────────────────────────────

ONBOARDING_TEXT = (
    "👋 Привет! Я <b>{bot_name}</b> — публикую посты из чатов в канал.\n\n"
    "<b>Что я умею:</b>\n"
    "• Ответь на любое сообщение в чатах с этим ботом + упомяни <b>@{bot_name}</b> "
    'либо напиши ключевую фразу (по умолчанию "в движухи") → '
    "я опубликую его в канале с подписью автора и источника\n"
    "• Пришли мне пост в ЛС через <code>/post</code> → мастер с подтверждением\n"
    "• Поддерживаю текст, медиа и анонимные опросы (только репост)\n\n"
)

ONBOARDING_NOT_REGISTERED = (
    "✏️ Этого чата ещё нет в моём списке. "
    "Если хочешь в репостах ссылки на чат и пост, следуй инструкции ниже:\n"
    "• Cделай меня админом чата с правом: <b>Пригласительные ссылки</b>\n"
    "• Можно без прав админа, но тогда добавь постоянную ссылку на чат в ЛС\n\n"
    "<b>Замечание:</b> прямые ссылки на конкретное сообщение («Источник») "
    "работают только в супергруппах. Чтобы конвертировать обычную группу "
    "в супергруппу — в настройках чата включите «История чата». "
    "Иначе будет видна ссылка на чат без прямой ссылки на сообщение.\n\n"
    "Выберите действие:"
)

ONBOARDING_ALREADY_REGISTERED = (
    "✅ Этот чат уже есть в моём списке — больше ничего делать не нужно."
)

ONBOARDING_BLOCKED_CHAT = "🚫 Этот чат в чёрном списке — публикация из него запрещена."

ONBOARDING_BLOCKED_HINT = "Чтобы снова разрешить публикацию, админ бота должен снять блок через ЛС."

ONBOARDING_BTN_ADMIN_CONFIRM = "🔒 Создать ботом ссылку с подтверждением вступления"
ONBOARDING_BTN_ADMIN_OPEN = "🔓 Создать ботом ссылку без подтверждения"
ONBOARDING_BTN_MEMBER = "✏️ Добавить чат без ссылки"
ONBOARDING_BTN_LEAVE = "❌ Убрать бота"

# Имена ссылок-приглашений (видны в списке ссылок группы; лимит Telegram — 32 символа).
ONBOARDING_LINK_NAME_CONFIRM = "С подтверждением вступления"
ONBOARDING_LINK_NAME_OPEN = "Без подтверждения"

ONBOARDING_NOT_INVITER = "Только тот, кто добавил меня, может настраивать."
ONBOARDING_LEAVE_ACK = "Пока!"
ONBOARDING_LEAVE_DONE = "👋 Я ушёл из чата. Если понадоблюсь снова — добавьте меня."
ONBOARDING_GET_CHAT_FAILED = "Не удалось получить информацию о чате."
ONBOARDING_GET_MEMBER_FAILED = (
    "Не удалось проверить мои права. Попробуйте позже или добавьте без прав."
)
ONBOARDING_NEED_ADMIN_RIGHTS = (
    "Я пока не админ с правом «Пригласительные ссылки».\n\n"
    "<b>Как исправить:</b>\n"
    "1. Откройте настройки чата\n"
    "2. Раздел «Администраторы»\n"
    "3. Добавьте меня с правом «Пригласительные ссылки»\n"
    "4. Снова нажмите кнопку создания ссылки\n\n"
    "Или добавьте чат без ссылки кнопкой «✏️ Добавить чат без ссылки»."
)
ONBOARDING_EXPORT_FAILED = (
    "Не смог создать ссылку-приглашение. Попробуйте выдать право "
    "«Пригласительные ссылки» или добавьте чат без прав."
)
ONBOARDING_NEED_SUPERGROUP = (
    "Ссылки с подтверждением вступления работают только в супергруппах.\n\n"
    "Включите «Историю чата» в настройках группы, чтобы превратить её в "
    "супергруппу, и нажмите кнопку ещё раз."
)
# Общий блок-предупреждение для всех итоговых сообщений с ссылкой.
# Используется через f-строку в ONBOARDING_ADMIN_DONE / ONBOARDING_LINK_*_DONE.
ONBOARDING_ADMIN_DONE_IMPORTANT = (
    "⚠️ <b>Важно:</b> ссылка-приглашение создана мной и пропадёт, если у меня "
    "заберут права админа «Пригласительные ссылки». Чтобы ссылка была "
    "постоянной, добавьте её через мастер <code>/add_chat</code> в ЛС.\n\n"
    "<b>Прямые ссылки на сообщение («пост»)</b> работают только в "
    "супергруппах. Если это обычная группа — в настройках чата включите "
    "«История чата», чтобы конвертировать её в супергруппу."
)
ONBOARDING_ADMIN_DONE = (
    f"✅ Чат добавлен! В подписях постов будет ссылка на чат.\n\n{ONBOARDING_ADMIN_DONE_IMPORTANT}"
)
ONBOARDING_LINK_CONFIRM_DONE = (
    f"✅ Чат добавлен! Создана ссылка <b>с подтверждением вступления</b>: "
    "вступающие подают заявку, её одобряют админы чата.\n\n"
    f"{ONBOARDING_ADMIN_DONE_IMPORTANT}"
)
ONBOARDING_LINK_OPEN_DONE = (
    f"✅ Чат добавлен! Создана ссылка <b>без подтверждения</b>: вступающие "
    "присоединяются сразу.\n"
    "⚠️ Если в настройках группы включено «Одобрять новых участников», "
    "подтверждение всё равно потребуется — эта настройка сильнее ссылки.\n\n"
    f"{ONBOARDING_ADMIN_DONE_IMPORTANT}"
)
ONBOARDING_MEMBER_DONE_CHAT = (
    "✅ Чат добавлен в ограниченном режиме.\n"
    "Подпись пока что будет показывать название чата без ссылки.\n"
    "Инструкции по добавлению ссылки направлены в личку добавившему бота."
)
ONBOARDING_MEMBER_DONE_PM = (
    "✅ Чат «{name}» добавлен в ограниченном режиме.\n"
    "Подпись пока что будет показывать название чата без ссылки.\n\n"
    "Чтобы добавить постоянную ссылку — используйте мастер <code>/add_chat</code> "
    "Помимо пригласительной ссылки тебе пригодится его id: <code>{chat_id}</code> "
    "Если в начале не -100, то добавь перед id"
)

# ────────────────────────────────────────────────────────────────────────────
# add_chat — регистрация чата по ссылке (ЛС)
# ────────────────────────────────────────────────────────────────────────────

ADD_CHAT_INTRO = (
    "✏️ <b>Мастер добавления чатов</b>\n\n"
    "Мастер нужен, чтобы добавлять постоянные ссылки независимо от прав бота в чате.\n"
    "От тебя потребуется id чата, текущее имя чата и постоянная пригласительная ссылка на чат.\n"
    "Я их буду запрашивать последовательно.\n\n"
    "Для начала отправь id чата.\n\n"
    "{howto}"
)

ADD_CHAT_CANCEL_HINT = "\nЧтобы отменить — /cancel."

ADD_CHAT_ID_HOWTO = (
    "<b>Как узнать id чата:</b>\n"
    "• С помощью бота <code>@userinfobot</code> или других подобных.\n"
    "• В Telegram Desktop: Настройки → Дополнительно → «Показывать ID», "
    "затем в настройках чата → «Копировать ID».\n\n"
    "id чата — это число, у групп/каналов обычно вида <code>-1001234567890</code> "
    "(с -100 в начале). В настройках, обычно, не хватает -100 перед номером."
)

ADD_CHAT_CANCELLED = "Отменено."

ADD_CHAT_EXISTS_WITH_LINK = (
    "Чат уже есть: «{name}» (ссылка есть). Продолжаю — имя и ссылку можно обновить."
)

ADD_CHAT_EXISTS_NO_LINK = "Чат уже есть: «{name}» (без ссылки). Продолжаю — добавлю ссылку."

ADD_CHAT_BAD_ID = (
    "Не удалось распознать id. Пришли число — обычно вида "
    "<code>-1001234567890</code> (с минусом).\n\n"
    "{howto}"
)

ADD_CHAT_ASK_NAME = "Теперь отправь текущее имя чата."

ADD_CHAT_NAME_CONFLICT = (
    "⚠️ Имя «{name}» уже используется другим чатом. Рекомендую поменять имя, чтобы не путаться."
)

ADD_CHAT_ASK_LINK = (
    "Теперь отправь постоянную пригласительную ссылку — например "
    "<code>https://t.me/+abc</code> или <code>https://t.me/username</code>."
)

ADD_CHAT_SUCCESS = "Готово! Чат «{name}» добавлен в список с постоянной ссылкой."

ADD_CHAT_BAD_LINK = (
    "Некорректная ссылка. Отправь ссылку вида <code>https://t.me/+abc</code> "
    "или <code>https://t.me/username</code>."
)

ADD_CHAT_NOT_IN_CHAT = (
    "Не могу подтвердить, что ты состоишь в этом чате. Убедись, что и ты, и бот "
    "являетесь участниками чата, и повтори отправку ссылки."
)

ADD_CHAT_LINK_PROTECTED = (
    "У этого чата уже есть ссылка, созданная ботом. Заменить её может только администратор бота."
)

# ────────────────────────────────────────────────────────────────────────────
# Wizard — мастер создания поста в ЛС
# ────────────────────────────────────────────────────────────────────────────

WIZARD_INTRO = (
    "📝 <b>Мастер создания поста</b>\n\n"
    "Пришли мне текст или медиа — я задам пару вопросов и опубликую.\n"
    "Чтобы отменить — /cancel."
)

WIZARD_CANT_OPEN = "Не могу открыть мастер."
WIZARD_PM_ONLY = "Мастер работает только в ЛС."
WIZARD_NO_CATEGORIES = "Нет доступных категорий. Обратись к администратору."
WIZARD_PICK_CATEGORY = "🏷 Выбери категорию поста:"
WIZARD_COLLECTING = "📸 Собираю пост..."
WIZARD_ALBUM_READY = "Пост из {count} элементов готов. Выбери категорию:"
WIZARD_CATEGORY_NOT_FOUND = "Категория не найдена. Начни заново с /post."
WIZARD_CONFIRM = "Категория: <b>{category}</b>. Подтверди публикацию:"
WIZARD_BTN_PUBLISH = "✅ Опубликовать"
WIZARD_BTN_CANCEL = "❌ Отмена"
WIZARD_CANCELLED = "Отменено."
WIZARD_SESSION_STALE = "Сессия устарела. Начни заново с /post."
WIZARD_ALBUM_STALE = "Пост устарел (прошло больше часа). Начни заново с /post."
WIZARD_UNKNOWN_KIND = "Неизвестный тип поста. Начни заново с /post."
WIZARD_PUBLISH_FAILED = (
    "Не получилось опубликовать пост. Попробуй ещё раз или обратись к администратору."
)
WIZARD_INTERNAL_ERROR = "Внутренняя ошибка. Попробуй ещё раз."
WIZARD_PUBLISHED = "✅ Пост опубликован в канал."

# ────────────────────────────────────────────────────────────────────────────
# Repost — публикация через реплай+упоминание
# ────────────────────────────────────────────────────────────────────────────

REPOST_BLOCKED_CHAT = "🚫 Публикация из этого чата запрещена."
REPOST_NO_CATEGORIES = "Нет доступных категорий. Обратись к администратору."
REPOST_PICK_CATEGORY = "🏷 Выбери категорию поста:"
CHAT_NOT_REGISTERED_HINT = (
    "ℹ️ Этот чат не зарегистрирован по новой схеме: посты публикуются без "
    "ссылки-приглашения. Удалите и заново добавьте бота в чат или выполните "
    "/add_chat в личке."
)
REPOST_ONLY_AUTHOR = "Только автор может выбрать категорию."
REPOST_STALE = "Пост устарел. Повтори реплай с упоминанием бота."
REPOST_PUBLISH_FAILED = (
    "Не получилось опубликовать пост. Попробуй ещё раз или обратись к администратору."
)

PUBLISH_BOT_NOT_IN_CHANNEL = (
    "⚠️ Бот временно не имеет доступа к главному каналу — публикация недоступна. "
    "Обратись к администратору."
)
POST_TOO_LONG = (
    "Пост слишком длинный для репоста: {length} символов при лимите {limit}. "
    "Сократи текст и попробуй снова."
)

PUBLISHED_TEXT = "✅ Пост опубликован в канале."
PUBLISHED_ALBUM = "✅ Пост опубликован в канале ({count} элементов)."
PUBLISHED_ALBUM_FALLBACK = (
    "✅ Пост опубликован в канале.\n"
    "<i>Внимание: скопировано только это фото — кэш остальных был недоступен "
    "(возможно, бот недавно перезапускался).</i>"
)

REPOST_POLL_CONFIRM = (
    "Этот опрос будет переслан в канал как репост от {author}.\n"
    "Подпись и категория не добавятся — результаты опроса будут общими с чатом. "
    "Переслать?"
)
POLL_BTN_FORWARD = "✅ Переслать"

# ────────────────────────────────────────────────────────────────────────────
# Posts — /myposts, /posts, редактирование/удаление
# ────────────────────────────────────────────────────────────────────────────

POSTS_INSTRUCTIONS = (
    "ℹ️ Чтобы обновить пост: сначала отредактируй исходное сообщение "
    "(в ЛС или в чате), потом нажми «Обновить».\n"
    "Альбомы и опросы переделать нельзя, как и исправить ошибку — "
    "только 🗑 Удалить и опубликовать заново."
)

MY_POSTS_TITLE = "🔍 <b>Мои последние посты:</b>"
MY_POSTS_EMPTY = "У тебя пока нет постов."
RECENT_POSTS_TITLE = "🔍 <b>Последние посты</b> (до {limit}):"
RECENT_POSTS_EMPTY = "Постов пока нет."
POSTS_STAFF_ONLY = "Только админ может смотреть чужие посты."

POST_BTN_EDIT = "🔄 Обновить"
POST_BTN_EDIT_ALBUM = "🔄 Обновить текст"
POST_BTN_DELETE = "🗑 Удалить"

POST_NOT_FOUND = "Пост не найден или уже удалён."
POST_NOT_AUTHOR = "Только автор поста или админ."
POST_NOT_TRACKED = "Пост не отслеживается (старый пост)."
POST_TOO_OLD = "Пост старше 48 часов — удаление невозможно."
POST_DELETED = "🗑 Пост удалён."
POST_EDIT_NOT_CHANGED = (
    "Пост не менялся — обновлять нечего. Можно 🗑 удалить и 📝 опубликовать заново."
)
POST_EDIT_UNSUPPORTED = "Обновить можно только текст/фото/видео/документ."
POST_EDIT_KIND_CHANGED = (
    "Тип контента изменился (текст ↔ медиа) — на месте обновить нельзя. "
    "Удали пост и опубликуй заново."
)
POST_EDIT_FAILED = "Не получилось обновить пост."
POST_EDITED_ALBUM = "✅ Пост обновлён — только текст (альбом, медиа не меняется)."
POST_EDITED = "✅ Пост обновлён."
POST_UNKNOWN_ACTION = "Неизвестное действие."

# ────────────────────────────────────────────────────────────────────────────
# Admin — пользователи, контакты, категории, статистика
# ────────────────────────────────────────────────────────────────────────────

ADMIN_ONLY = "Только админ может использовать эту команду."
ADMIN_ONLY_SHORT = "Только админ."
BACKUP_NOT_FOUND = "Файл БД не найден: <code>{path}</code>"
BACKUP_SENT = "Бэкап отправлен."
UNKNOWN_USER = "Не знаю такого пользователя — он ещё ни разу не писал боту."

USERS_HELP = (
    "<b>Управление пользователями</b>\n\n"
    "<code>/users list</code> — список всех\n"
    "<code>/users set &lt;id|@username&gt; allow|blocked|staff [reason] [pm|mention|both]</code>\n"
    "<code>/users block &lt;id|@username&gt; [reason] [pm|mention|both]</code>\n"
    "<code>/users unblock &lt;id|@username&gt;</code>\n"
)

USERS_SET_EXAMPLE = "Пример: <code>/users set @username allow</code>"
USERS_ROLE_NAMES = "Роль: unknown / allow / blocked / staff"
USERS_ROLE_SET = "Пользователь <code>{id}</code> → <b>{role}</b>"
USERS_ROLE_SET_REASON_SUFFIX = " (причина: {reason})"
USERS_BLOCK_EXAMPLE = "Пример: <code>/users block @username спам pm</code>"
USERS_BLOCKED = "Заблокирован <code>{id}</code>: {reason} ({mode})"
USERS_BLOCKED_NO_REASON = "без причины"
USERS_UNBLOCK_EXAMPLE = "Пример: <code>/users unblock @username</code>"
USERS_UNBLOCKED = "Доступ выдан: <code>{id}</code>"
USERS_LIST_EMPTY = "Пользователей пока нет."

# ── Пользователи: FSM-потоки из меню (id/алиас → роль/причина) ───────────────

USERS_ASK_TARGET = (
    "Отправь id или @username пользователя (он должен был хоть раз писать боту).\nОтмена — /cancel."
)
USERS_ASK_TARGET_BAD = (
    "Не нашёл пользователя. Отправь id или @username того, кто уже писал боту, либо /cancel."
)
USERS_ASK_ROLE = "Выбери роль для <code>{ref}</code>:"
USERS_PICK_ROLE_HINT = "Нажми одну из кнопок выше или /cancel."
USERS_ASK_REASON = (
    "Отправь причину блокировки или <code>-</code>, чтобы заблокировать без причины.\n"
    "Отмена — /cancel."
)
USERS_STALE = "Сессия устарела — начни заново из меню «Пользователи»."

USERS_ROLE_BTN_UNKNOWN = "👤 Пользователь"
USERS_ROLE_BTN_ALLOW = "✅ Доступ"
USERS_ROLE_BTN_BLOCKED = "🚫 Заблокировать"
USERS_ROLE_BTN_STAFF = "👑 Админ"

CONTACTS_HELP = (
    "<b>Контакты админов</b>\n\n"
    "<code>/admin_contacts list</code>\n"
    "<code>/admin_contacts add &lt;id|@username&gt; &lt;роль&gt; [комментарий]</code>\n"
    "<code>/admin_contacts remove &lt;id&gt;</code>\n"
    "<code>/admin_contacts order &lt;id&gt; &lt;число&gt;</code>\n\n"
    "Добавлять можно по числовому id или по @username (если пользователь уже писал "
    "боту). Узнать id — <code>/users list</code>, там у каждого показан <code>id:...</code>."
)

CONTACTS_ADD_EXAMPLE = "Пример: <code>/admin_contacts add @username owner главный админ</code>"
CONTACTS_USER_NOT_FOUND = (
    "Пользователь не найден. Укажи числовой id (см. <code>/users list</code>) "
    "или @username того, кто уже писал боту."
)
CONTACTS_SAVED = "Контакт <code>{id}</code> сохранён."
CONTACTS_REMOVE_EXAMPLE = "Пример: <code>/admin_contacts remove 123</code>"
CONTACTS_BAD_ID = "Некорректный id."
CONTACTS_REMOVED = "Контакт <code>{id}</code> удалён."
CONTACTS_ORDER_EXAMPLE = "Пример: <code>/admin_contacts order 123 10</code>"
CONTACTS_ORDER_BAD = "Порядок — целое число."
CONTACTS_ORDER_MISSING = "Контакт не найден. Сначала /admin_contacts add."
CONTACTS_ORDER_DONE = "Порядок <code>{id}</code> → {order}."
CONTACTS_LIST_EMPTY = "Контактов пока нет."

CATEGORIES_HELP = (
    "<b>Категории постов</b>\n\n"
    "<code>/categories list</code> — список категорий\n"
    "<code>/categories add &lt;название&gt;</code>\n"
    "<code>/categories remove &lt;id&gt;</code>\n"
    "<code>/categories order &lt;id&gt; &lt;число&gt;</code>\n"
    "<code>/categories hide|show &lt;id&gt;</code>\n\n"
    "id категории виден в <code>/categories list</code>."
)

CATEGORIES_ADD_EXAMPLE = "Пример: <code>/categories add Недвижимость</code>"
CATEGORIES_EXISTS = "Такая категория уже есть."
CATEGORIES_ADDED = "Категория добавлена: <b>{name}</b>."
CATEGORIES_REMOVE_HINT = (
    "Укажи id категории: <code>/categories remove 3</code> (см. <code>/categories list</code>)."
)
CATEGORIES_NOT_FOUND = "Категория не найдена."
CATEGORIES_REMOVED = "Категория удалена: <b>{name}</b>."
CATEGORIES_ORDER_EXAMPLE = "Пример: <code>/categories order 3 5</code>"
CATEGORIES_ORDER_BAD = "Порядок — целое число."
CATEGORIES_BAD_ID = "Некорректный id категории."
CATEGORIES_ORDER_DONE = "Порядок категории <code>{id}</code> → {order}."
CATEGORIES_SHOW_EXAMPLE = "Пример: <code>/categories {sub} 3</code>"
CATEGORIES_HIDDEN = "Категория скрыта."
CATEGORIES_SHOWN = "Категория показана."
CATEGORIES_LIST_EMPTY = "Категорий пока нет."
CATEGORIES_HIDDEN_MARKER = " <i>(скрыта)</i>"
CATEGORY_LINE = "<code>{id}</code> {name} (порядок {order}){status}"

# ── Категории: FSM-потоки из меню (текущий список — хинтом) ──────────────────

CATEGORIES_CURRENT = "<b>Текущие категории:</b>\n{list}"
CATEGORIES_ADD_ASK = "\n\nОтправь название новой категории.\nОтмена — /cancel."
CATEGORIES_REMOVE_ASK = "\n\nОтправь <b>id</b> категории для удаления.\nОтмена — /cancel."
CATEGORIES_HIDE_ASK = "\n\nОтправь <b>id</b> категории, которую нужно скрыть.\nОтмена — /cancel."
CATEGORIES_SHOW_ASK = "\n\nОтправь <b>id</b> категории, которую нужно показать.\nОтмена — /cancel."
CATEGORIES_ORDER_ASK = (
    "\n\nОтправь пары <code>id:порядок</code> через запятую, например: "
    "<code>3:1, 1:2</code>\nОтмена — /cancel."
)
CATEGORIES_BAD_ID_INPUT = "Отправь числовой id категории, либо /cancel."
CATEGORIES_ORDER_PARSE_BAD = (
    "Не понял формат. Пример: <code>3:1, 1:2</code> — пары <code>id:порядок</code> через запятую."
)
CATEGORIES_ORDER_DONE_ALL = "Порядок категорий обновлён."

STATS_HELP = (
    "<b>Статистика публикаций</b>\n\n"
    "<code>/stats</code> — последние 10 публикаций\n"
    "<code>/stats &lt;число&gt;</code> — последние N (до 50)\n"
    "<code>/stats categories</code> — по категориям\n"
    "<code>/stats users</code> — по пользователям\n"
    "<code>/stats user &lt;@username|id&gt;</code> — по конкретному пользователю"
)

STATS_USER_EXAMPLE = "Пример: <code>/stats user @restwin</code>"
STATS_USER_NOT_FOUND = "Пользователь не найден."
STATS_USER_EMPTY = "У этого пользователя нет публикаций."
STATS_RECENT_EMPTY = "Публикаций пока нет."
STATS_RECENT_HEADER = "<b>Последние публикации</b> (всего: {total}):\n"
STATS_BY_CATEGORY_HEADER = "<b>Публикации по категориям:</b>"
STATS_BY_USER_HEADER = "<b>Публикации по пользователям:</b>"
STATS_CATEGORY_NONE = "без категории"
STATS_USER_HEADER = "<b>Публикации {name}</b> (всего: {total}):\n"
STATS_SOURCE_PM = "из ЛС"
STATS_SOURCE_CHAT = "из «{name}»"
STATS_SOURCE_UNKNOWN = "из чата"

# ────────────────────────────────────────────────────────────────────────────
# Links — ссылки сообщества
# ────────────────────────────────────────────────────────────────────────────

LINKS_ADMIN_ONLY = "Только админ может управлять ссылками."
LINKS_HEADER = "<b>Ссылки сообщества:</b>\n\n"
LINKS_LINE = "{icon} {label}: {value}\n"
LINKS_EMPTY_VALUE = "<i>не заполнена</i>"
LINKS_USAGE = (
    "Задать: <code>/links rules|channel|chat &lt;ссылка&gt;</code>\n"
    "Очистить: <code>/links clear rules|channel|chat</code>"
)
LINKS_CLEAR_KEY = "Ключ: rules / channel / chat."
LINKS_CLEARED = "{label} — ссылка очищена."
LINKS_SET_EXAMPLE = "Пример: <code>/links {key} https://t.me/...</code>\nСсылка должна начинаться с http(s):// или t.me/."
LINKS_BAD_KEY = "Ключ: rules / channel / chat. Или /links clear &lt;key&gt;."
LINKS_BAD_URL = (
    "Это не похоже на ссылку. Отправь ссылку (начинается с http(s):// или t.me/) или /cancel."
)
LINKS_UNKNOWN_KEY = "Ошибка: неизвестная ссылка. Начни заново из меню «Ссылки»."
LINKS_SAVED = "Сохранено: {label}.\n\n"

LINK_LABEL_RULES = "Правила публикации постов"
LINK_LABEL_CHANNEL = "Канал"
LINK_LABEL_CHAT = "Основной чат"

# ────────────────────────────────────────────────────────────────────────────
# Chat manage — управление чатами
# ────────────────────────────────────────────────────────────────────────────

CHAT_MANAGE_ADMIN_ONLY = "Только админ может использовать эту команду."
CHAT_LIST_EMPTY = "Список чатов пуст. Используй <code>/add_chat</code>."
CHAT_LIST_LINE_LINK = (
    '{marker}🔗 <a href="{link}">{name}</a> <code>id: {chat_id}</code>\n'
    "<code>{link}</code>\n👤 добавил: {who}"
)
CHAT_LIST_LINE_NO_LINK = (
    "{marker}🔗 {name} <code>id: {chat_id}</code>\n"
    "<i>нет ссылки (нет прав админа)</i>\n👤 добавил: {who}"
)
CHAT_ADDED_BY_UNKNOWN = "неизвестно"
CHAT_REMOVE_EXAMPLE = "Пример: <code>/remove_chat Полное название чата</code> или <code>/remove_chat -1001234567890</code>"
CHAT_REMOVED = "Чат «{name}» удалён из списка."
CHAT_REMOVE_NOT_FOUND = "Чат «{name}» не найден в списке."
CHAT_BLOCK_EXAMPLE = "Пример: <code>/block_chat Название чата --- причина</code> (можно по id)"
CHAT_BLOCK_NOT_FOUND = "Чат «{name}» не найден в списке."
CHAT_AMBIGUOUS_NAME = (
    "Найдено несколько чатов с именем «{name}» — уточни по id "
    "(число, обычно <code>-1001234567890</code>)."
)
CHAT_BLOCKED = "Публикация из «{name}» запрещена{reason}."
CHAT_BLOCK_REASON_PREFIX = " (причина: {reason})"
CHAT_UNBLOCK_EXAMPLE = "Пример: <code>/unblock_chat Полное название чата</code> (можно по id)"
CHAT_UNBLOCKED = "Публикация из «{name}» снова разрешена."
CHAT_ADMIN_LOST = (
    "⚠️ Я потерял права админа в чате «{name}» — ссылка-приглашение, которую я создавал, "
    "больше не работает. Верните мне права админа («Пригласительные ссылки») или добавьте "
    "постоянную ссылку через мастер <code>/add_chat</code>."
)
CHAT_BOT_REMOVED = "Меня удалили из чата «{name}» — я убрал его из списка чатов."
CHAT_BOT_REMOVED_BLOCKED = "Меня удалили из чата «{name}», но этот чат в чёрном списке — я не могу убрать его из списка чатов."
CHAT_REGISTERED_NOTIFY = (
    "✅ Вы добавили бота в чат «{name}». Вам будут приходить уведомления "
    "при изменении его состояния в этом чате."
)
CHAT_BLOCKED_NOTIFY = (
    "Чат «{name}» заблокирован администратором бота. Публикация из него запрещена."
)
CHAT_UNBLOCKED_NOTIFY = "Чат «{name}» разблокирован. Публикация из него снова разрешена."

# ────────────────────────────────────────────────────────────────────────────
# Chat manage FSM — управление чатами из меню (имя или id + отмена)
# ────────────────────────────────────────────────────────────────────────────

CHAT_REMOVE_ASK = (
    "🗑 Отправь имя чата или его id (обычно <code>-1001234567890</code>).\nОтмена — /cancel."
)
CHAT_BLOCK_ASK = (
    "🚫 Отправь имя чата или его id (обычно <code>-1001234567890</code>).\nОтмена — /cancel."
)
CHAT_UNBLOCK_ASK = (
    "✅ Отправь имя чата или его id (обычно <code>-1001234567890</code>).\nОтмена — /cancel."
)
CHAT_BLOCK_ASK_REASON = (
    "Отправь причину блокировки (она будет показана авторам постов) "
    "или <code>-</code>, чтобы заблокировать без причины.\nОтмена — /cancel."
)
CHAT_BAD_TARGET = (
    "Не похоже на имя или id. Отправь имя чата или id "
    "(например <code>-1001234567890</code>), либо /cancel."
)

# ────────────────────────────────────────────────────────────────────────────
# Меню (inline) — названия кнопок
# ────────────────────────────────────────────────────────────────────────────

MENU_BTN_BACK = "⬅️ Назад"
MENU_BTN_CREATE_POST = "📝 Создать пост"
MENU_BTN_MY_POSTS = "🔍 Мои посты"
MENU_BTN_ALL_POSTS = "📋 Все посты"
MENU_BTN_ADD_CHAT = "➕ Добавить чат"
MENU_BTN_ALL_CHATS = "📋 Все чаты"
MENU_BTN_MY_CHATS = "📋 Мои чаты"
MENU_BTN_CHAT_MANAGE = "🗑🚫 Управление"
MENU_BTN_CATEGORIES = "🏷 Категории"
MENU_BTN_USERS = "👥 Пользователи"
MENU_BTN_STATS = "📊 Статистика"
MENU_BTN_HELP = "ℹ️ Помощь"
MENU_BTN_CONTACTS = "📇 Админы бота"
MENU_BTN_LINKS = "🔗 Ссылки"
MENU_BTN_VERSION = "ℹ️ Версия"
MENU_BTN_BACKUP = "🗄 Бэкап БД"
MENU_BTN_RULES = "📜 Правила публикации постов"
MENU_BTN_CHANNEL = "📢 Канал"
MENU_BTN_MAIN_CHAT = "💬 Основной чат"

# Пагинация списков (пользователи / чаты).
MENU_BTN_PAGE_FIRST = "⏮"
MENU_BTN_PAGE_PREV = "◀"
MENU_BTN_PAGE_NEXT = "▶"
MENU_BTN_PAGE_LAST = "⏭"
LIST_PAGE_MARKER = "{page}/{pages}"
LIST_RANGE = "<i>Показано {start}–{end} из {total}</i>"

MENU_BTN_REMOVE_CHAT = "🗑 Удалить чат"
MENU_BTN_BLOCK_CHAT = "🚫 Заблокировать"
MENU_BTN_UNBLOCK_CHAT = "✅ Разблокировать"

MENU_BTN_USERS_LIST = "👀 Список пользователей"
MENU_BTN_USERS_SET = "➕ Назначить роль"
MENU_BTN_USERS_BLOCK = "🚫 Заблокировать"
MENU_BTN_USERS_UNBLOCK = "✅ Разблокировать"

MENU_BTN_CONTACTS_LIST = "👀 Список контактов"
MENU_BTN_CONTACTS_ADD = "➕ Добавить контакт"
MENU_BTN_CONTACTS_REMOVE = "➖ Удалить контакт"
MENU_BTN_CONTACTS_ORDER = "↕️ Порядок"

MENU_BTN_CATEGORIES_ADD = "➕ Добавить"
MENU_BTN_CATEGORIES_REMOVE = "➖ Удалить"
MENU_BTN_CATEGORIES_ORDER = "↕️ Упорядочить"
MENU_BTN_CATEGORIES_HIDE = "🙈 Скрыть"
MENU_BTN_CATEGORIES_SHOW = "👁 Показать"

MENU_BTN_STATS_RECENT = "🕘 Последние 10"
MENU_BTN_STATS_CATEGORIES = "🏷 По категориям"
MENU_BTN_STATS_USERS = "👤 По пользователям"
MENU_BTN_STATS_USER = "🔎 По пользователю"

MENU_BTN_LINKS_RULES = "📜 Правила публикации постов"
MENU_BTN_LINKS_CHANNEL = "📢 Канал"
MENU_BTN_LINKS_CHAT = "💬 Основной чат"
MENU_BTN_LINKS_SHOW = "👀 Показать текущие"

CATEGORY_BTN_CANCEL = "❌ Отмена"

# ────────────────────────────────────────────────────────────────────────────
# Контент — неподдерживаемые типы
# ────────────────────────────────────────────────────────────────────────────

UNSUPPORTED_CONTENT = "Такой контент публиковать нельзя — только текст и медиа."
NON_ANONYMOUS_POLL = "Неанонимные опросы публиковать нельзя (ограничение Telegram)."

# ────────────────────────────────────────────────────────────────────────────
# Прочее
# ────────────────────────────────────────────────────────────────────────────

CANCELLED = "Отменено."
ADMIN_VIEW_STAFF_ONLY = "Только админ может смотреть чужие посты."
LONG_ANSWER_HINT = "📌 См. сообщение ниже"

# Заголовки экранов меню (с двоеточием — отличаются от названий кнопок).
ADMINS_HEADER = "<b>Админы:</b>\n"
ADMINS_EMPTY = "(пусто)"
CHAT_MANAGE_TITLE = "🗑🚫 Управление чатами:"
USERS_TITLE = "👥 Пользователи:"
CONTACTS_TITLE = "📇 Админы бота:"
CATEGORIES_TITLE = "🏷 Категории:"
STATS_TITLE = "📊 Статистика:"
LINKS_TITLE = "🔗 Ссылки:"

LINKS_SET_PROMPT = "Отправь ссылку (начинается с http(s):// или t.me/), или /cancel."

# Подсказки по использованию команд (меню «?»).
HINT_CONTACTS_ADD = (
    "Используй: <code>/admin_contacts add &lt;id|@username&gt; &lt;роль&gt; [комментарий]</code>"
)
HINT_CONTACTS_REMOVE = "Используй: <code>/admin_contacts remove &lt;id&gt;</code>"
HINT_CONTACTS_ORDER = "Используй: <code>/admin_contacts order &lt;id&gt; &lt;число&gt;</code>"
HINT_STATS_USER = "Используй: <code>/stats user &lt;@username|id&gt;</code>"
HINT_BACKUP_DB = "Используй: <code>/backup_db</code> — файл БД уйдёт в отладочные чаты."
BACKUP_DISABLED = "Бэкапы осуществляются на сервере. Функциональность бэкапа в отладочный чат отключена."

# Throttling (rate-limit notice).
THROTTLED = "Слишком часто — подожди секунду."

# ────────────────────────────────────────────────────────────────────────────
# Подпись поста (post_builder) — фрагменты строки подписи
# ────────────────────────────────────────────────────────────────────────────

POST_SIG_FROM_LINK = " из "
POST_SIG_FROM_QUOTED = " из «{name}»"
POST_SIG_POST_LINK = "пост"
POST_SIG_PM_SUFFIX = " · из ЛС"
POST_SIG_NO_CHAT_TITLE = "чата"

# ────────────────────────────────────────────────────────────────────────────
# Справка /help и каталог команд (help_text)
# ────────────────────────────────────────────────────────────────────────────

CMD_DESC_COMMON = {
    "menu": "открыть меню",
    "post": "создать пост (в ЛС)",
    "myposts": "мои посты: обновить/удалить",
    "add_chat": "добавить чат (мастер)",
    "cancel": "отменить мастер поста",
    "recheck": "перепроверить доступ",
    "whyblocked": "почему ограничен доступ",
    "contacts": "админы бота",
    "help": "помощь",
}

CMD_DESC_ADMIN = {
    "get_all_chats": "список всех чатов",
    "remove_chat": "удалить чат (по названию или id)",
    "block_chat": "запретить публикацию из чата (с причиной)",
    "unblock_chat": "разрешить публикацию из чата",
    "users": "управление пользователями",
    "admin_contacts": "редактировать контакты админов",
    "categories": "управление категориями постов",
    "stats": "статистика публикаций",
    "posts": "последние посты (обновить/удалить)",
    "links": "управление ссылками сообщества",
    "show_admins": "список админов",
    "backup_db": "бэкап БД (в отладочные чаты)",
    "version": "версия бота",
}

HELP_COMMON_SECTION = (
    "<b>Команды (в ЛС):</b>\n"
    "/menu — меню\n"
    "/post — мастер создания поста\n"
    "/myposts — мои посты (обновить/удалить)\n"
    "/add_chat — добавить чат (мастер)\n"
    "/cancel — отменить мастер\n"
    "/whyblocked — причина ограничения доступа\n"
    "/contacts — админы бота\n"
    "/recheck — перепроверить доступ\n"
    "/help — эта справка"
)

HELP_ADMIN_SECTION = (
    "\n\n<b>Команды админа:</b>\n"
    "/get_all_chats — список всех чатов\n"
    "/remove_chat &lt;название|id&gt; — удалить чат из списка\n"
    "/block_chat &lt;название|id&gt; --- причина — запретить публикацию из чата\n"
    "/unblock_chat &lt;название|id&gt; — снять запрет публикации\n"
    "/users list|set|block|unblock — управление пользователями\n"
    "/admin_contacts add|remove|list|order — каталог админов\n"
    "/categories list|add|remove|order|hide|show — категории постов\n"
    "/stats [N|categories|users|user] — статистика публикаций\n"
    "/posts [N] — последние посты (обновить/удалить)\n"
    "/links [rules|channel|chat] — ссылки сообщества (правила, канал, чат)\n"
    "/show_admins — список админов\n"
    "/backup_db — выгрузить БД в отладочные чаты\n"
    "/version — версия бота"
)

# ────────────────────────────────────────────────────────────────────────────
# Стартовые данные (seed) и значения по умолчанию
# ────────────────────────────────────────────────────────────────────────────

# Категории постов на свежей БД; правятся в рантайме через /categories.
DEFAULT_POST_CATEGORIES = [
    "🐳 Движуха!",
    "Запросы и просьбы",
    "Самореклама",
    "Иное",
]

# Ключевая фраза репоста по умолчанию (переопределяется REPOST_TRIGGER_PHRASES).
DEFAULT_REPOST_TRIGGERS = ["в движухи"]
