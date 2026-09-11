# スロット天井ボーダー計算アプリ

ホールで実戦中にiPhoneブラウザから開き、「今の周期数などから続行すべきか」を判断するための補助ツール。設定判別は行わない。天井・周期ベースの簡易判定に絞っている。

本ツールは情報整理を目的とし、実際の遊技判断は自己責任で行うこと。掲載しているしきい値は攻略サイト情報の集約であり公式一次情報ではない。

## アーキテクチャ

- `engine/`: 機種非依存の判定エンジン。機種固有の分岐は一切書かない
- `profiles/*.yaml`: 機種ごとのデータ(入力軸・判定ルール)。新機種はYAMLを1つ追加するだけで対応できる
- `services/sheets_log.py`: 実戦ログをGoogle Sheetsに永続化(Streamlit Cloudはアプリ再起動でローカルファイルが消えるため)
- `ui/`: axesから動的にフォーム・結果画面を生成
- `app.py`: 上記を配線するエントリポイント

## 1. ローカルでのセットアップ

```bash
python -m venv .venv
.venv\Scripts\activate        # Windows PowerShellの場合: .venv\Scripts\Activate.ps1
pip install -r requirements.txt

copy .streamlit\secrets.toml.example .streamlit\secrets.toml
# .streamlit\secrets.toml を編集して app_password 等を設定(このファイルはgit管理外)

streamlit run app.py
```

## 2. Google Sheets連携の準備(実戦ログの永続化・無料)

Streamlit Community Cloudはアプリ再起動(スリープ復帰・再デプロイ)でローカルファイルが消えるため、実戦ログはGoogle Sheetsに保存する。

1. https://console.cloud.google.com/ でGCPプロジェクトを新規作成(無料枠内)
2. 「APIとサービス」から **Google Sheets API** と **Google Drive API** を有効化
3. 「認証情報」→「サービスアカウントを作成」→ 作成後、そのサービスアカウントの「鍵」タブから **JSON形式の鍵を新規作成・ダウンロード**
4. Googleドライブ上で実戦ログ用の新しいスプレッドシートを作成
5. そのスプレッドシートの「共有」から、サービスアカウントのメールアドレス(JSON鍵の`client_email`)を**編集者**として共有
6. ダウンロードしたJSON鍵の中身を `.streamlit/secrets.toml` の `[gcp_service_account]` セクションに、スプレッドシートのURLに含まれるID(`https://docs.google.com/spreadsheets/d/【ここ】/edit`)を `sheet_id` に、それぞれ設定する

## 3. GitHubへのpush

Streamlit Community CloudはGitHubリポジトリからコードを読み込んでデプロイする仕組みのため、pushが必要。

1. https://github.com で空のリポジトリを新規作成(Public/Privateどちらでも可。README等は追加しない)
2. 作成後に表示されるリポジトリのURL(例: `https://github.com/xxxxx/slot-evassist-too.git`)を確認
3. このプロジェクトフォルダで以下を実行(`<URL>`は自分のリポジトリURLに置き換える)

```bash
git add -A
git commit -m "Initial commit: v1 scaffold"
git branch -M main
git remote add origin <URL>
git push -u origin main
```

## 4. Streamlit Community Cloudへのデプロイ

1. https://share.streamlit.io にGitHubアカウントでログイン
2. 「New app」→ 対象リポジトリ・ブランチ(`main`)・メインファイル(`app.py`)を指定してDeploy
3. デプロイ後、アプリの「Settings」→「Secrets」に `.streamlit/secrets.toml` と同じ内容を貼り付ける(このファイル自体はGitHubにはpushされていない)
4. 発行されたURLをiPhoneのブラウザのホーム画面に追加しておくと、ホールでワンタップでアクセスできる

## 新機種の追加方法

`profiles/` に新しいYAMLファイルを追加するだけでよい。`axes`(入力項目)・`derived`(派生変数)・`ev_lookup`/`tables`(期待値テーブル参照)・`rules`(判定条件)を機種ごとに定義すれば、エンジン(`engine/rules.py`)・UI(`ui/forms.py`)・ログ機構(`services/sheets_log.py`)のコードは変更不要。機種が2つ以上になると、起動時に機種選択のカード画面が自動で表示される。

## ヘッダー画像について

機種選択画面・判定画面の上部に画像を出したい場合、`assets/` フォルダに自分で用意した画像ファイル(自撮りの筐体写真など、著作権的に問題のないもの)を置き、該当する `profiles/*.yaml` の `header_image` に相対パス(例: `assets/monkey_turn_v.jpg`)を設定する。メーカーの版権キャラクターアート等をネットから拾って使うのは著作権上避けること。
