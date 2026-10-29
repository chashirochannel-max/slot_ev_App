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

機種選択画面・判定画面の上に出る画像は、「その台が何の台か一目でわかる目印」のためのもの。正確な絵である必要はないので、**基本は自作のバッジ画像を使う**。

### 基本:自作バッジ(著作権の心配なし)

`scripts/make_badge.py` が、色・短い機種名・単純な図形(波、炎、星など)だけでバッジを作る。キャラクター・ロゴ・公式画像は一切使っていないので、著作権の心配がない。

1. このフォルダでコマンドを開き、次のどちらかを実行する
   - 1機種だけ作る: `python scripts/make_badge.py <machine_id>`(例: `python scripts/make_badge.py sao2`)
   - 全機種まとめて作る: `python scripts/make_badge.py --all`
2. `assets/badges/<machine_id>.jpg`(800x400)ができる
3. `profiles/<machine_id>.yaml` の `header_image` の行を、次のように書きかえる
   ```yaml
   header_image: "assets/badges/<machine_id>.jpg"
   ```

**色・短い名前・図形を変えたいとき**は、`scripts/make_badge.py` の上の方にある `BADGES` という表を書きかえて、もう一度実行する。

- `short`: 大きく出す名前。`
` を入れると2行になる(例: `"リコリス
リコイル"`)
- `colors`: 背景の (上の色, 下の色)
- `accent`: 図形とラベルの色
- `motif`: 図形の種類(boat, flame, moon, train, stage など。表の下の `MOTIFS` に一覧がある)

**マスコット版**: `python scripts/make_badge.py --all --style mascot` で、このアプリ専用のオリジナルマスコット「おもち」が機種ごとの小物(ヘルメット、刀、花束など)を持ったバッジが `assets/badges_mascot/<machine_id>.jpg` にできる。使うときは `header_image` を `"assets/badges_mascot/<machine_id>.jpg"` にする。小物・向き・大きさは `make_badge.py` の `MASCOTS` 表で変えられる。作品のキャラクターに似せた絵(デフォルメ・ちび化を含む)は著作権の問題になるので描かない。

表に無い新しい機種は、名前から自動で色を決めた汎用デザインになる(そのままでも使える)。左上の「スマスロ」「Lパチスロ」のラベルは、YAMLの `name` の先頭から自動で決まる。

### 公式画像を使っている機種(6機種)を自作バッジに切りかえる方法

fire_force2 / kabaneri_kaimon_kessen / l_sengoku_musume5 / monkey_turn_v / toaru_index2 / world_dystar は、今はメーカー公式画像(`assets/<machine_id>.jpg`)を使っている。バッジもすでに `assets/badges/` に作ってあるので、切りかえるなら:

1. `profiles/<machine_id>.yaml` を開く
2. `header_image: "assets/<machine_id>.jpg"` の行を `header_image: "assets/badges/<machine_id>.jpg"` に書きかえる(1行だけ)
3. 元にもどしたいときは、その行をもとの文字に戻す(公式画像のファイルは消していない)

### 公式画像を使う場合の注意

- メーカーの画像には著作権がある。今はパスワード付きの個人利用アプリという前提で、光さんの判断で一部に使っている
- **ほかの人に配ったり、パスワードなしで公開したりするなら、公式画像はやめて自作バッジにする**
- 公式画像を新しく入れるときは、必ず `python scripts/process_header_image.py <元画像のパス> <machine_id>` に通して800x400にそろえる(機種ごとにカードの高さがバラバラにならないように)。出力は `assets/<machine_id>.jpg`

## トラブル時

| 症状 | 原因 | 対処 |
|---|---|---|
| アプリを開くと「Oh no. Error running app.」と出る(PC・iPhone問わず) | コードのバグではなく、**Streamlit CloudのGitHub連携が切れている**ことが多い(2026-09-18に発生。原因不明・GitHub側で失効していた)。「Manage app」のログに`Failed to download the sources for repository`と出ていれば確定 | 1. share.streamlit.io にログイン → 右上メニュー→ Settings → **Linked accounts**<br>2. 「Streamlit does not have access to private repos on this GitHub account」の**「Connect here」**をクリック<br>3. GitHubの認証画面で「Public and private」への許可を求められるので **Authorize**<br>4. 元のアプリの「Manage app」→ **Reboot app** |
| 上記の確認方法 | - | 「Manage app」ボタン(画面右下の赤いボタン)を押すとログが見られる。`Failed to download the sources`とあればリポジトリ接続の問題 |
