# 週1回の自動メンテ手順(Claudeの定期タスク用)

毎週月曜の朝に、Claudeの定期タスクがこの手順どおりに動く。
人(光さん)がやるのは、最後の報告を読んで「送っていいよ」と言うことだけ。

- 見るもの: slot-toolbox.com(天井期待値ページ)と 1geki.jp(新台カレンダー)
- 作るもの: 新機種のプロファイル(YAML)とサムネイル、既存機種の数値の更新
- **mainへの取り込みとGitHubへのpushは、光さんの「送っていいよ」があるまで絶対にしない**

## 絶対に守ること

1. **pushしない・mainにマージしない**(手順gで光さんの承認後に、通常のセッションで行う)
2. `.streamlit/secrets.toml` や鍵ファイル(`*.json` の認証情報など)は**開かない・読まない**
3. 期待値などの数値は **curlで取った生HTMLの表から転記**する。WebFetchの要約は数値の出典にしない。**値を推測で埋めない**(取れない値は「未取得」と書いて止める)
4. サムネイルは自作の図形とマスコット「おもち」だけ。**公式キャラ・ロゴ・パネル画像・公式の書体をまねしない**
5. 1回の実行で新しく作る機種は**最大4機種**。それ以上は「来週分」として報告に書く
6. アクセスは控えめに(リクエストの間は2秒以上あける。必要なページだけ取る)
7. 実戦ログ(Google Sheets)には検証中に書きこまない(`scripts/verify_app.py` が自動で遮断する)

## a. 準備と検出

```powershell
cd C:\Users\sauza\my-project\slot-evassist-too
git checkout main
git pull
.venv\Scripts\python.exe scripts\check_updates.py
```

- 終了コード `0` = 変化なし、`10` = 何か見つかった、`1` = エラー
- レポートは `reports\update_YYYY-MM-DD.md`(gitには入らない)
- 作業ツリーに未コミットの変更があるとき(`git status` で確認)は、手をつけずに光さんへ報告して終わる

## b. 変化なし(終了コード0)のとき

状態を保存して1行で終わる。

```powershell
.venv\Scripts\python.exe scripts\check_updates.py --update-state
```

報告例:「今週は変更なしでした(新しい天井ページ0件・出典の更新0件)」

※ 状態ファイル `data/update_state.json` が変わった場合は、main上で
`git commit -m "更新チェックの状態を保存"`(末尾にCo-Authored-By行)までしてよい。pushはしない。

## エラー(終了コード1)のとき

何も直さず、レポートのエラー内容を光さんに伝えて終わる。状態ファイルは書きかわっていない。

## c. 何か見つかった(終了コード10)とき

```powershell
git checkout -b auto/YYYY-MM-DD   # 例: auto/2026-11-02
```

### c-1. 新しい天井ページ(新機種の候補)

レポートの「新しい天井ページ」の表を上から順に見て、**対象かどうか**を決める。

対象外(作らない。報告に「対象外: 理由」と書くだけ):
- パチンコ(タイトルに「P」「e」「パチンコ」など)
- 沖スロ・ノーマル(A)タイプなど、AT機ではないもの(新台カレンダーの「タイプ」列も参考にする)
- すでにプロファイルがある機種(`profiles\*.yaml` の `name:` を確認。続編・派生機は別機種)
- 期待値表がまだ載っていない(「調査中」「近日公開」など)ページ

対象の機種(最大4機種)ごとに:

1. 生HTMLを取る(数値はここから読む)
   ```bash
   curl -s -A "Mozilla/5.0" https://slot-toolbox.com/<slug>-tenjo/ -o <スクラッチ>/<slug>.html
   ```
2. `profiles\<id>.yaml` を作る。書き方は既存の最近のファイル(`profiles\aobuta.yaml`、`profiles\mahoako.yaml`、`profiles\juoh.yaml` など)にそろえる
   - 先頭のコメントに【機種情報】【天井システム】と、**出典URLと取得日**を書く
     (例: `# 出典: https://slot-toolbox.com/<slug>-tenjo/ (2026年11月2日取得、curlで生HTML取得)`)
     ※ このURLがファイル内にあることで、翌週から「出典の更新」の見張り対象になる
   - 期待値表は行を省略せず、周期・モード等の区切りをまたいで補間しない(CLAUDE.md「機種追加時の調査ガイドライン」)
   - 表にない値・読めない値は作らない。わからない点は notes に「未確認」と書く
   - `header_image: "assets/badges_mascot/<id>.jpg"` にする
3. `scripts\make_badge.py` の `BADGES` と `MASCOTS` に1行ずつ足す
   - 色・短い名前・小物(`props`)は**一般的なモチーフだけ**(例: 帽子、剣、マイク)。作品固有のキャラ・ロゴ・衣装を再現しない
   - 既存の `PROPS` にあるものだけを使う(新しい小物を描く場合も円・線・多角形だけ)
4. その機種だけサムネイルを作る(全機種の作り直しはしない)
   ```powershell
   .venv\Scripts\python.exe scripts\make_badge.py <id> --style mascot
   .venv\Scripts\python.exe scripts\make_badge.py <id>
   ```

5機種目以降は作らず、`--defer` で来週に回す(手順e)。

「参考: 既存プロファイルがある機種の天井ページ(出典は別サイト)」に出たものは、
新機種ではない。今のプロファイルの数値と表を見比べ、大きく違えば報告に書く(数値は変えない)。

### c-2. 既存機種の出典ページ更新

lastmod(最終更新日時)が変わっただけで、中身の数値は同じことが多い(サイト全体の一括更新もある)。

1. その出典ページの生HTMLをcurlで取る
2. 期待値表の数値をプロファイルの `tables` と1行ずつ見比べる
3. - **数値が変わっていた**: YAMLの数値を出典どおりに直し、ヘッダーコメントに
     「YYYY年M月D日再取得: ○○の行を△△→□□に更新」と書く
   - **文章だけ変わっていた**(新しい恩恵情報など): 数値は変えない。報告に「何が増えたか」だけ書く
   - **変化なし**: 報告に「数値の変化なし」と書く

## d. 検証

```powershell
.venv\Scripts\python.exe scripts\verify_app.py --sheet <新機種id1> <新機種id2>
```

- 全プロファイルの読み込み、機種選択画面と全機種の画面(ゲーム数300で判定ボタンまで)を AppTest で動かす
- 実戦ログのGoogle Sheets書きこみは、ダミーsecretsと書きこみ関数の差しかえで**遮断**される
  (「Sheetsへの接続試行(すべて遮断済み)」の回数が出るだけで、外には送られない)
- 制御文字の混入チェック(profiles と make_badge.py)
- `--sheet` で新サムネイルの一覧画像 `reports\thumbs_YYYY-MM-DD.jpg` ができる
- 最後に `OK: 問題なし`(終了コード0)が出るまで直す。直せないときは、その機種をブランチから外して報告に書く

## e. ブランチにコミット

```powershell
git add profiles\<id>.yaml scripts\make_badge.py assets\badges\<id>.jpg assets\badges_mascot\<id>.jpg
git commit -m "自動メンテ: 新機種○○・××を追加、△△の期待値を更新

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"

.venv\Scripts\python.exe scripts\check_updates.py --update-state --defer <来週に回すslug> --defer <...>
git add data\update_state.json
git commit -m "更新チェックの状態を保存

Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>"
```

- `--update-state` は**プロファイルを作った後**に実行する(新しい出典URLの基準日時もここで記録される)
- 対象外と判断したページは `--defer` しない(確認済みになり、来週は出ない)
- 4機種の上限で作らなかったページは `--defer <slug>` を付ける(未確認のまま残り、来週また出る)
- `git add -A` は使わない(関係ないファイルや一時ファイルを入れないため)
- **pushしない・mainにマージしない**

## f. 光さんへの報告(中学生にもわかる言葉で)

次の形で書く。専門用語は使わず、わからないことはわからないと書く。

```
今週のチェック結果です。

■ 見つかったもの
- 新しい機種: ○機種(△△、××)
- 数字が変わった機種: ○機種
- 来週に回した機種: ○機種(□□)
- 対象外にしたもの: ○件(理由: パチンコ など)

■ 主な数字
| 機種 | 天井 | 短くなる条件 | 期待値の例(300G) | 期待値の例(500G) |
|---|---|---|---|---|
| … | … | … | … | … |

■ 新しいサムネイル
C:\Users\sauza\my-project\slot-evassist-too\reports\thumbs_YYYY-MM-DD.jpg

■ 自信がないところ
- (例: リセット後の天井が出典1つだけで、ほかのサイトで確かめられていない)

■ 動作確認: 全○機種で画面エラー0件

今は auto/YYYY-MM-DD という作業用の場所に置いてあり、アプリにはまだ出ていません。
「送っていいよ」と言えば、mainに取り込んでGitHubへ送ります(送るとアプリに反映されます)。
```

## g. 光さんが「送っていいよ」と言ったら(通常のセッションで)

```powershell
cd C:\Users\sauza\my-project\slot-evassist-too
git checkout main
git pull
git merge --no-ff auto/YYYY-MM-DD
.venv\Scripts\python.exe scripts\verify_app.py
git push origin main
git branch -d auto/YYYY-MM-DD
```

- マージで衝突したら止めて光さんに報告する
- `verify_app.py` がNGならpushしない
- 光さんが「この機種はやめて」と言ったら、その機種のファイルだけ戻してから取り込む

## 実行が飛んだとき(PCの電源が切れていた等)

- 状態ファイルは「前回の確認時点」を覚えているので、**次に動いたときにまとめて検出される**。特別な作業はいらない
- 何週もたまって新機種が多いときも、1回4機種まで。残りは `--defer` で翌週以降へ
- 手で今すぐ回したいときは、通常のセッションで「AUTO_UPDATE.mdの手順で今週分をやって」と頼めばよい
- 前回の auto/ ブランチが残っている(まだ承認されていない)ときは、新しいブランチを作らずに
  光さんへ「前回分が未承認です」と先に知らせる(前回分を承認してから今回分を作る)

## 参考: check_updates.py の仕組み

- slot-toolbox.com のサイトマップ(`sitemap_index.xml` → `post-sitemap.xml`)だけを読み、
  `-tenjo/` で終わるページと lastmod を集める。本体ページは新機種候補のタイトル取得時だけ読む
- profiles の本文に書かれた slot-toolbox.com のURLを、その機種の「出典」とみなして lastmod を見張る
- 出典を別サイトにしている既存機種(かのかり、モンキーターンV など)の対応表は、
  スクリプト内の `SLUG_ALIASES` にある。新しく「既存機種なのに新機種候補に出た」ものがあれば、ここに足す
- 状態ファイル `data/update_state.json`: 確認済みの天井ページURLと、出典ごとの前回 lastmod(個人情報なし)
- 初回だけは、lastmod が21日以内の天井ページを新機種候補として残し、それより古いものは確認済みにした
