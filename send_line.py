from linebot import LineBotApi
from linebot.models import TextSendMessage
import time
import pyotp
import re
from playwright.sync_api import sync_playwright
import os
import firebase_admin
from firebase_admin import credentials, db
from firebase_admin import firestore
from linebot.v3.messaging import Configuration, ApiClient, MessagingApi, BroadcastRequest, TextMessage
from dotenv import load_dotenv

load_dotenv()

MAIL_OMU = "sh23701v@st.omu.ac.jp"
OMUID = "sh23701v"
PASSWORD = os.environ.get("LONG_PASSWORD")
TOTP_OMU = os.environ.get("TOTP_OMU")
FORM_URL = "https://omunet.sharepoint.com/sites/kagai/SitePages/%E6%95%99%E5%AE%A4%E7%AD%89%E3%81%AE%E4%BA%88%E7%B4%84-%E5%85%A8%E5%AD%A6%E5%85%B1%E9%80%9A%E6%95%99%E8%82%B2%E7%AD%89%EF%BC%8F1%E5%8F%B7%E9%A4%A8%EF%BC%8F%E6%B3%95%E5%AD%A6%E9%83%A8%E6%A3%9F%EF%BC%8F%E5%AD%A6%E7%94%9F%EF%BE%8E%EF%BD%B0%EF%BE%99%EF%BC%8F%E7%94%B0%E4%B8%AD%E8%A8%98%E5%BF%B5%E9%A4%A8%EF%BC%8F%E9%9F%B3%E6%A5%BD%E7%B7%B4%E7%BF%92%E5%AE%A4%EF%BC%8F%E5%90%88%E5%AE%BF%E6%89%80%E4%BB%96.aspx"


def send_monthly_broadcast():
    with sync_playwright() as p:
        # ブラウザを起動 (headless=False で動作が見えるようにします)
        print("ブラウザを起動中...")
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(locale="ja-JP")
        page = context.new_page()

        print(f"フォームにアクセス中: {FORM_URL}")
        page.goto(FORM_URL)

        # 1. Microsoft ログイン
        print("Microsoft ログイン中...")
        page.wait_for_selector('input[type="email"]')
        page.fill('input[type="email"]', MAIL_OMU)
        page.click('input[type="submit"]')

        # 2. OMU 認証システム
        print("OMU 認証システムでログイン中...")
        # ユーザー名とパスワードの入力
        try:
            page.wait_for_selector('input[name="SM_UID"]', timeout=20000)
            page.fill('input[name="SM_UID"]', OMUID)
            page.fill('input[name="SM_PWD"]', PASSWORD)
            time.sleep(0.5)
            page.click('input[type="submit"]')
        except Exception as e:
            print(f"OMUログイン画面の待機中にエラーが発生しました: {e}")
            # 別のセレクタを試行
            page.fill('input[id*="user"]', OMUID)
            page.fill('input[id*="pass"]', PASSWORD)
            page.click('button:has-text("ログイン")')

        # 3. ワンタイムパスワード
        print("ワンタイムパスワードを生成・入力中...")
        totp = pyotp.TOTP(TOTP_OMU)
        token = totp.now()
        print(f"現在のトークン: {token}")

        try:
            # OTP入力フィールドを待機
            page.wait_for_selector('input[name*="SM_PWD"]', timeout=15000)
            page.fill('input[name*="SM_PWD"]', token)
            page.click('input[type="submit"]')
        except Exception as e:
            print(f"OTP入力画面の待機中にエラーが発生しました: {e}")
            # 万が一フィールド名が異なる場合
            page.fill('input[type="text"]', token)
            page.keyboard.press("Enter")

        # 4. サインイン状態の維持
        try:
            page.wait_for_selector('#idSIButton9', timeout=10000)
            page.click('#idSIButton9') # 「はい」をクリック
        except:
            pass

        print("\nログインが完了しました！")
        print("SharePointのページ読み込みを待機しています...")
        
        # ページ内の要素が表示されるまで少し待つ
        try:
            page.wait_for_load_state("networkidle", timeout=10000)
        except Exception:
            pass
        time.sleep(3) # 念入りに待機

        print("ページ内の要素を読み込むためにスクロールしています...")
        # 動的に読み込まれるページ（遅延読み込み）に対応するため、徐々にスクロールします
        # SharePoint等は一度に一番下までスクロールしても読み込まれないことがあるため分けてスクロールします。
        for _ in range(15):
            page.keyboard.press("PageDown")
            page.mouse.wheel(0, 800)
            time.sleep(1)
            
        time.sleep(2) # 最後の読み込み待機

        print("\n=== 「教室」または「ｽﾌﾟﾚｯﾄﾞ」を含むリンクを抽出 ===")
        try:
            # locator.evaluate_all を使ってJavaScript側で一括取得する(高速かつ安定)
            links_data = page.locator("a").evaluate_all(
                "elements => elements.map(e => ({ text: e.innerText, ariaLabel: e.getAttribute('aria-label'), href: e.href }))"
            )
            
            print(f"ページ内の <a> タグの数: {len(links_data)}")
            print(links_data)
            found = False
            factor=[]
            url=[]

            for data in links_data:
                text = data.get("text") or ""
                aria_label = data.get("ariaLabel") or ""
                href = data.get("href") or ""
                
                # 「教室」または「ｽﾌﾟﾚｯﾄﾞ」が含まれるかチェック
                if href and ("月教室" in text or "月教室" in aria_label or "ｽﾌﾟﾚｯﾄﾞ" in text or "ｽﾌﾟﾚｯﾄﾞ" in aria_label):
                    label = text.strip() if text.strip() else aria_label.strip()
                    print(f"要素名: {label}")
                    print(f"URL: {href}")
                    print("-" * 30)
                    factor.append(label)
                    url.append(href)
                    found = True

            if not found:
                print("目的のリンクは見つかりませんでした。")
                
        except Exception as e:
            print(f"ページ内操作中にエラーが発生しました: {e}")
        #期限取得
        try:
            deadline_text=["",""]
            deadline_text[0] = page.locator("span:has-text('月施設仮予約')").nth(0).inner_text()
            deadline_text[1] = page.locator("span:has-text('月施設仮予約')").nth(1).inner_text()
            sum_deadline_text=deadline_text[0]+deadline_text[1]
            print(f"合わせた文章: {sum_deadline_text}")
            # ドット（.）が改行も含むように re.DOTALL を使うのがコツです
            # 1つ目の ( ) は「当月」の後のカッコ内
            # 2つ目の ( ) は「翌月」の後のカッコ内
            pattern = r"＜当　月＞.*?（(.*?入力締切).*?＜翌　月＞.*?（(.*?入力締切)"

            # re.DOTALL を指定することで、複数行にまたがって検索できます
            current_month = ""
            next_month = ""
            match = re.search(pattern, sum_deadline_text, re.DOTALL)
            if match:
                current_month = match.group(1) # 当月の分
                next_month = match.group(2)    # 翌月の分
            
        except Exception as e:
            print(f"エラーが発生しました: {e}")
            # 処理終了後すぐにブラウザが閉じないように待機します
        cred = credentials.Certificate("service-account.json")
        firebase_admin.initialize_app(cred)
        db = firestore.client()
        OK = db.collection('latest_broadcast').document('text').get().to_dict().get("Confirm")
        message_text=[f"{factor[0][2:]}({current_month})\nリンク：{url[0]}",f"{factor[1][2:]}({next_month})\nリンク：{url[1]}"]
        if OK:
            try:
                LINE_ACCESS_TOKEN = os.environ.get("LINE_ACCESS_TOKEN")
                line_bot_api = LineBotApi(LINE_ACCESS_TOKEN)
                # 送りたいメッセージの内容
                message=[]
                message.append(TextSendMessage(text=message_text[0]))
                message.append(TextSendMessage(text=message_text[1]))
                
                # 友だち全員に一斉送信（ブロードキャスト）
                line_bot_api.broadcast(message)
                print("友だち全員への送信に成功しました。")
                
            except Exception as e:
                print(f"エラーが発生しました: {e}")
                # 処理終了後すぐにブラウザが閉じないように待機します
                input("ブラウザを閉じるにはEnterキーを押してください...")
        
        def set_data_with_id():
            doc_id = "text"
            # .set() を使うと、指定したIDで保存されます（既存なら上書き）
            db.collection("latest_broadcast").document(doc_id).update({"0": message_text[0]})
            db.collection("latest_broadcast").document(doc_id).update({"1": message_text[1]})
            print(f"ドキュメント {doc_id} に{data}を保存しました")

        set_data_with_id()

if __name__ == "__main__":
    send_monthly_broadcast()