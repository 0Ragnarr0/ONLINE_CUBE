# コンテナのレシピ

# ベースイメージ
# python:3.11 -> python3.11が入ったLinux環境
# slim -> 最小限の構成(ファイルサイズが小さい)
FROM python:3.11-slim

# 作業ディレクトリを作成
WORKDIR /app

# websocketsをインストールする準備
# requirements.txtをコンテナ側にコピーする
COPY requirements.txt .

# 必要なPythonライブラリをインストール
# RUN -> ビルド時に実行されるコマンド(作ったときだけ)
# --nocache-dir -> キャッシュを残さない(コンテナを軽くする)
RUN pip install --no-cache-dir -r requirements.txt

# ソースコードをコンテナに全てコピー
COPY . .

# ポートの指定
# ここはコメントのようなもので、実際のポート指定はdocker-compose.ymlの方で行う
EXPOSE 8765

# サーバーの起動コマンド
# ターミナルでpython server.pyを実行するのと同じ
# CMD -> コンテナ起動時に実行される
CMD ["python", "server.py"]