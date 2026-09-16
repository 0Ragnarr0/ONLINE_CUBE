# ============================================================
# server.py  ──  WebSocket ゲームサーバー
# ============================================================
# このファイルの役割:
#   ・複数のUnityクライアントからの接続を受け付ける
#   ・各プレイヤーの座標を受け取り、他の全員に転送する
#   ・プレイヤーの参加・退出を管理する
# ============================================================

import asyncio   # 非同期処理（複数のクライアントを同時に扱うために必要）
import json      # JSON形式のデータを読み書きする
import os        # 環境変数（Renderが渡すPORT）を読むために使う
import http      # ヘルスチェック応答用のHTTPステータス
import websockets  # WebSocket通信を実現するライブラリ（requirements.txtでインストール）


# ============================================================
# グローバル変数（サーバー全体で共有するデータ）
# ============================================================

# 現在接続中のプレイヤーを全員分保存する辞書
# 例: { 1: {"ws": <接続オブジェクト>, "x": 3.5, "z": -1.2},
#        2: {"ws": <接続オブジェクト>, "x": 0.0, "z":  2.0} }
players = {}

# 次に参加するプレイヤーに割り振るID番号（1から始まって増えていく）
next_id = 1


# ============================================================
# handler 関数 ── プレイヤー1人につき1つ動く関数
# ============================================================
# 新しいプレイヤーが接続するたびに、この関数が自動で呼ばれます。
# async def にすることで、複数のプレイヤーが同時に接続しても
# それぞれ並行して処理できます（非同期処理）。
async def handler(websocket):
    global next_id  # 関数の外にある next_id を書き換えるために必要

    # ── 参加処理 ─────────────────────────────────────────────
    # 新しいプレイヤーにIDを割り振って、管理リストに追加する
    player_id = next_id
    next_id += 1
    players[player_id] = {
        "ws": websocket,  # この接続オブジェクトを使って後でメッセージを送る
        "x": 0.0,         # 初期X座標
        "z": 0.0          # 初期Z座標
    }

    print(f"[接続] Player{player_id} が参加しました (現在{len(players)} 人)")

    # 参加したプレイヤーに「あなたはPlayer○○です」と伝える
    # また、すでに参加しているプレイヤーの座標も一緒に送る
    # （後から来た人が既存プレイヤーのキューブを表示できるようにするため）
    await websocket.send(json.dumps({
        "type": "joined",        # メッセージの種類
        "player_id": player_id,  # あなたのプレイヤーID
        "players": {             # 今いる全プレイヤーの座標一覧
            str(pid): {"x": p["x"], "z": p["z"]}
            for pid, p in players.items()  # 辞書の全要素をループ
        }
    }))

    # 他のプレイヤーに「新しい人が来ましたよ」と通知する
    # exclude_id=player_id とすることで、自分自身には送らない
    await broadcast({
        "type": "player_joined",  # メッセージの種類
        "player_id": player_id,   # 参加したプレイヤーのID
        "x": 0.0,                 # 初期座標
        "z": 0.0
    }, exclude_id=player_id)

    # ── メッセージ受信ループ ──────────────────────────────────
    try:
        # `async for` で接続が切れるまでずっとメッセージを待ち続ける
        # Unityからメッセージが届くたびに中の処理が実行される
        async for raw_message in websocket:

            # 受け取ったのは文字列（JSON形式）なので、辞書に変換する
            data = json.loads(raw_message)

            # "type" フィールドで「何の情報か」を判別する
            if data["type"] == "move":
                # プレイヤーが移動した → 座標を更新して全員に知らせる

                # サーバー側の座標記録を更新
                players[player_id]["x"] = data["x"]
                players[player_id]["z"] = data["z"]

                # 他の全プレイヤーに転送（自分には送らない）
                await broadcast({
                    "type": "player_update",      # 誰かが動いたという通知
                    "player_id": player_id,        # 誰が動いたか
                    "x": data["x"],                # 新しいX座標
                    "z": data["z"]                 # 新しいZ座標
                }, exclude_id=player_id)

    except websockets.exceptions.ConnectionClosed:
        # ゲームを閉じたり、ネットワークが切れたときはここに来る
        # エラーではなく正常な終了なので pass（何もしない）
        pass

    finally:
        # ── 退出処理 ─────────────────────────────────────────
        # try / except のどちらで終わっても必ずここが実行される
        del players[player_id]  # 管理リストから削除
        print(f"[切断] Player{player_id} が退出しました (残り{len(players)} 人)")

        # 残っているプレイヤーに「○○が退出しました」と通知
        await broadcast({
            "type": "player_left",
            "player_id": player_id
        })


# ============================================================
# broadcast 関数 ── 全員にメッセージを一斉送信する
# ============================================================
# exclude_id を指定すると、そのプレイヤーだけ送信をスキップできる
# （自分が動いた情報を自分に送り返す必要はないため）
async def broadcast(message, exclude_id=None):
    if not players:
        return  # 誰もいなければ何もしない

    data = json.dumps(message)  # 辞書 → JSON文字列に変換

    # 全プレイヤーへの送信タスクを一覧にする（除外対象はスキップ）
    tasks = [
        p["ws"].send(data)
        for pid, p in players.items()
        if pid != exclude_id  # exclude_id と一致するプレイヤーは除く
    ]

    if tasks:
        # asyncio.gather で全員に「同時に」送信する（順番待ちなし）
        await asyncio.gather(*tasks)


# ============================================================
# health_check 関数 ── Renderのヘルスチェック用
# ============================================================
# RenderやブラウザがWebSocketではなく普通のHTTP GETで接続してきたとき、
# 200 OK を返して「サーバーは生きている」と伝える。
# WebSocketのアップグレード要求（Upgrade: websocket）の場合は None を返し、
# 通常どおりWebSocket接続として処理させる。
async def health_check(path, request_headers):
    if request_headers.get("Upgrade", "").lower() != "websocket":
        return http.HTTPStatus.OK, [("Content-Type", "text/plain")], b"OK\n"
    return None  # WebSocket接続はそのまま handler へ


# ============================================================
# main 関数 ── サーバーを起動する
# ============================================================
async def main():
    # Renderは待ち受けるポート番号を PORT 環境変数で渡してくる。
    # ローカル（Docker含む）では PORT が無いので 8765 を使う。
    port = int(os.environ.get("PORT", 8765))

    print("=" * 40)
    print("  オンラインゲーム WebSocket サーバー")
    print(f"  0.0.0.0:{port}")
    print("=" * 40)

    # 0.0.0.0 はすべてのIPアドレスからの接続を受け付けるという意味
    # localhost (127.0.0.1) だと自分のPCからしか繋がらないので注意
    async with websockets.serve(handler, "0.0.0.0", port, process_request=health_check):
        await asyncio.Future()  # この行で「ずっと動き続ける」状態になる


# このファイルを直接実行したときだけ main() を呼ぶ
# （他のファイルから import されたときは呼ばれない）
if __name__ == "__main__":
    asyncio.run(main())