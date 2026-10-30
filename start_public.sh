#!/bin/bash
# Запуск сайта с публичной ссылкой через туннель Cloudflare.
# Использование:  bash ~/Documents/ent-trainer/start_public.sh
# Остановить: Control + C (сервер и туннель закроются вместе).

cd "$(dirname "$0")" || exit 1
source venv/bin/activate || { echo "Не найдено виртуальное окружение venv"; exit 1; }

# Скачиваем cloudflared один раз (официальный релиз Cloudflare для Mac на Apple Silicon)
if [ ! -x .tools/cloudflared ]; then
  echo "Скачиваю cloudflared..."
  mkdir -p .tools
  curl -L -o .tools/cloudflared.tgz https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-arm64.tgz \
    && tar -xzf .tools/cloudflared.tgz -C .tools \
    || { echo "Не удалось скачать cloudflared"; exit 1; }
fi

# Сервер Django в фоне
python manage.py runserver 0.0.0.0:8000 &
SERVER_PID=$!
trap 'kill $SERVER_PID 2>/dev/null' EXIT
sleep 3

echo ""
echo "=============================================================="
echo " Ниже появится ссылка вида https://....trycloudflare.com"
echo " Отправьте её людям. Не закрывайте это окно, пока идёт проверка."
echo "=============================================================="
echo ""
.tools/cloudflared tunnel --url http://127.0.0.1:8000
