#!/bin/bash

# Verifica se foi passada uma mensagem de commit
if [ -z "$1" ]; then
  echo "❌ Usa: ./git_push.sh \"mensagem do commit\""
  exit 1
fi

echo "📦 A adicionar ficheiros..."
git add .

echo "📝 A fazer commit..."
git commit -m "$1"

echo "🚀 A fazer push para origin/main..."
git push origin main

echo "✅ Push concluído com sucesso!"
