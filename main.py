import os
import hashlib
from datetime import date
from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import mysql.connector
import replicate

app = FastAPI()

# CORS設定（フロントエンドからの接続を許可）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 🌐 【画面表示設定】ブラウザで http://127.0.0 を開いたときに index.html を表示する
@app.get("/")
async def read_index():
    if os.path.exists("index.html"):
        return FileResponse("index.html")
    raise HTTPException(status_code=404, detail="index.html が見つかりません。")

# 🌐 ログインボタンの移動先「/swap-page」でも顔変換画面を開けるように対応しました！
@app.get("/swap-page")
async def read_swap_page():
    if os.path.exists("swap.html"):
        return FileResponse("swap.html")
    raise HTTPException(status_code=404, detail="swap.html が見つかりません。")

# 🌐 【画面表示設定】他のHTML画面（legal.htmlなど）も自動で読み込めるようにする
@app.get("/{filename}.html")
async def read_html(filename: str):
    file_path = f"{filename}.html"
    if os.path.exists(file_path):
        return FileResponse(file_path)
    raise HTTPException(status_code=404, detail=f"{file_path} が見つかりません。")


# 【環境設定】ReplicateのAPIトークン
os.environ["REPLICATE_API_TOKEN"] = "r8_36p22Hshjsh62HajGshahhaHjHShas72Hahs"

# 🛠️ MySQL（XAMPP）の接続設定
db_config = {
    "host": "127.0.0.1",
    "user": "root",
    "password": "",
    "database": "logintest_db"
}

def get_db_connection():
    return mysql.connector.connect(**db_config)

# 🔐 パスワードをハッシュ化（暗号化）する関数
def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


# 👤 アカウント新規登録の処理
@app.post("/register")
async def register_user(username: str = Form(...), email: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
        if cursor.fetchone():
            return JSONResponse(status_code=400, content={"message": "このユーザー名はすでに使用されています。"})

        hashed_pw = hash_password(password)
        cursor.execute(
            "INSERT INTO users (username, email, password) VALUES (%s, %s, %s)",
            (username, email, hashed_pw)
        )
        conn.commit()
        return {"message": "ユーザー登録が完了しました！"}
    except mysql.connector.Error as db_err:
        print(f"Database Error: {db_err}")
        return JSONResponse(status_code=500, content={"message": "データベースエラーが発生しました。"})
    finally:
        cursor.close()
        conn.close()


# 🔑 ログインの処理
@app.post("/login")
async def login_user(username: str = Form(...), password: str = Form(...)):
    conn = get_db_connection()
    cursor = conn.cursor()
    try:
        hashed_pw = hash_password(password)
        cursor.execute(
            "SELECT id FROM users WHERE username = %s AND password = %s",
            (username, hashed_pw)
        )
        user = cursor.fetchone()
        if user:
            return {"message": "ログイン成功！", "redirect": "/swap-page"}
        else:
            return JSONResponse(status_code=401, content={"message": "ユーザー名またはパスワードが間違っています。"})
    except mysql.connector.Error as db_err:
        print(f"Database Error: {db_err}")
        return JSONResponse(status_code=500, content={"message": "データベースエラーが発生しました。"})
    finally:
        cursor.close()
        conn.close()


# 🎭 【重要：修正】どんなURLの書き方で送られてきても、すべてここで受け取って処理します！
@app.post("/swap-face")
@app.post("/swap_face")
@app.post("/swapface")
async def swap_face(target_image: UploadFile = File(...), source_image: UploadFile = File(...)):
    user_id = 1
    today = date.today()

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute(
            "SELECT count FROM usage_limits WHERE user_id = %s AND usage_date = %s",
            (user_id, today)
        )
        row = cursor.fetchone()

        if row and row[0] >= 10:
            raise HTTPException(status_code=429, detail="本日の利用上限（10回）に達しました。")

        if target_image.content_type not in ["image/jpeg", "image/png"]:
            raise HTTPException(status_code=400, detail="JPEGまたはPNG画像のみ受け付けています。")

        target_bytes = await target_image.read()
        source_bytes = await source_image.read()

        try:
            output = replicate.run(
                "codeplugtech/face-swap:48f98642a8b9d997f7fa2032e54fb8cc3f5723b9d09f7a52e9e2f694bc0db7d6",
                input={
                    "target_image": target_bytes,
                    "source_image": source_bytes
                }
            )
        except Exception as replicate_err:
            print(f"Replicate API Error: {replicate_err}")
            raise HTTPException(status_code=502, detail="AI変換サーバーでエラーが発生しました。")

        if row:
            cursor.execute(
                "UPDATE usage_limits SET count = count + 1 WHERE user_id = %s AND usage_date = %s",
                (user_id, today)
            )
        else:
            cursor.execute(
                "INSERT INTO usage_limits (user_id, usage_date, count) VALUES (%s, %s, 1)",
                (user_id, today)
            )
        conn.commit()

        return {"result_url": output}

    except mysql.connector.Error as db_err:
        print(f"Database Error: {db_err}")
        raise HTTPException(status_code=500, detail="データベースエラーが発生しました。")

    finally:
        cursor.close()
        conn.close()
