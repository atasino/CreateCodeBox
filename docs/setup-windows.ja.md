この文書は、英語版（正本）[setup-windows.md](setup-windows.md) の翻訳です。食い違いがあれば英語版が優先します。

# Windows での準備

状態: **実際の Windows パソコンでは、まだ試していません。** 以下の手順は、目安として読んでください。このページ用の画面の写真は、まだ作っていません（`docs/img/README.md` を見てください）。

CreateCodeBox には Git Bash が要ります。Windows 上の Claude Code にも要ります。必要なものは、Claude Code、Git for Windows、Python 3 です。Git for Windows には Git Bash が入っています。Python は 3.8 以上が必要で、私たちが試したのは Mac 上の 3.9 です。

## 1. Git for Windows を入れる

https://git-scm.com/download/win から入手して、インストールします。インストーラーの選択肢は、最初に選ばれているままでかまいません。スタートメニューに「Git Bash」が加わります。

## 2. Python を入れる

https://www.python.org/downloads/ から Python 3 を入手します。インストーラーで、「Add python.exe to PATH」にチェックを入れます。バージョンは 3.8 以上が必要です。

## 3. Git Bash を開く

スタートメニューを開き、「Git Bash」と入力して、Enter キーを押します。このワークスペースのコマンドは、すべて Git Bash で打ちます。コマンドプロンプトは使わないでください。PowerShell は確かめていないので、それも使わないでください。

Git Bash に文字を貼り付けるには、Shift + Insert を押すか、ウィンドウの中で右クリックします。

入っているソフトを確かめます。1 行ずつ打ってください。

```
git --version
python --version
```

パソコンによっては、Python のコマンドが `python3` か `py` です。3 つのうちどれか 1 つで、3.8 以上のバージョンが出れば、それでかまいません。

## 4. Claude Code を入れる

Anthropic の公式の案内（https://code.claude.com/docs/en/overview）に従ってください。サインインに必要なものと料金は、その案内に書いてあります。そのあと、確かめます。

```
claude --version
```

## 5. CreateCodeBox を用意して始める

README に、1 文で始める方法があります。Claude Code に 1 文を貼り付けると、Claude が CreateCodeBox を用意します。この方法は、まだ実際のパソコンで試したことがありません。

**1 文でうまくいかないとき: 自分の手で用意します。** 先に、`/exit` と打って Claude Code を終了するか、2 つ目の Git Bash のウィンドウを開きます。そのあと、Git Bash に、次の 3 行を 1 行ずつ貼り付けます。1 行ごとに Enter キーを押します。

```
git clone https://github.com/atasino/CreateCodeBox.git ~/CreateCodeBox
cd ~/CreateCodeBox
claude
```

1 行目のアドレスは、このリポジトリのものです。別の人が用意した CreateCodeBox（GitHub 上のコードの置き場）を使うときは、1 行目の `https://` から `.git` までを、そのアドレスに置き換えてください。アドレスは、GitHub のページの緑の **Code** ボタンからコピーできます。ボタンを押して、コピーのアイコンを押します。1 行目は、CreateCodeBox をダウンロードして、ホームフォルダ（あなたのユーザー名のフォルダ。Windows ではユーザーフォルダ）の中の `CreateCodeBox` というフォルダに置きます。Git Bash では、`~` がそのユーザーフォルダを指します。2 行目で、そのフォルダに入ります。3 行目で、Claude Code を起動します。

初回は、Claude Code が、このフォルダを信頼してよいかを聞いてきます。貼り付けたアドレスから作ったフォルダで、そのアドレスを信頼できるなら、yes と答えます。

この 3 行のあとは、Claude Code が `CreateCodeBox` のフォルダで動いています。このウィンドウをそのまま使います。[README](../README.ja.md) の手順 4 は飛ばして、手順 5 に進み、作りたいアプリを Claude に伝えます。

## フォルダを置く場所

**おすすめ:** ホームフォルダの直下の、`CreateCodeBox` というフォルダ: `%USERPROFILE%\CreateCodeBox`（Git Bash では `~/CreateCodeBox`）。README の 1 文で始める方法も、この場所を使います。

**避ける場所:**

- **ダウンロード・デスクトップ・ドキュメント。** 同期のアプリが、これらのフォルダをクラウドにコピーすることがよくあります。作ったものや鍵のファイルが、パソコンの外に出てしまうかもしれません。ダウンロードしたファイルもここに入るので、外から来た `CLAUDE.md` ファイルが混ざるおそれもあります。
- **iCloud Drive・OneDrive・Dropbox が同期するフォルダ。** 作ったものがクラウドにコピーされるかもしれません。同期で、`.ws/` の中の記録が壊れることもあります。
- **ほかの Git のリポジトリの中。** Git が 2 つのプロジェクトを取り違えることがあります。外側のリポジトリの `CLAUDE.md` が読み込まれることもあります。
- **空白や、英語以外の文字を含むパス（ファイルの場所の書き方）。** そのようなパスで失敗するソフトがあります。Git Bash と Python のスクリプトが、よくある例です。
- **システムのフォルダ。** たとえば `C:\Windows`。作ったものが消されるかもしれません。管理者の権限が要ることもあります。

ワークスペースは、これを確かめます。`bash ws/bin/ws.sh doctor` を打ってください。`place: ok` か、理由つきの `place: warn` が出ます。警告は出しますが、止めはしません。

## 知っておくこと

- Claude が「別のターミナルを開いてください」と言ったら、2 つ目の Git Bash のウィンドウを開きます。
- 強化モード（hardened mode）は、Claude が実行するコマンドに、鍵のファイルを読ませないようにする、任意の設定です。OS の仕組みで止めます。Windows では、まだ使えません。
- ワークスペースから Python 3.8 以上が必要だと表示されたときは、手順 2 と、手順 3 の `python` の行を確かめます。
- うまくいかないときは、`cd ~/CreateCodeBox` でそのフォルダに入り、そこで `bash ws/bin/ws.sh doctor` を打ちます。
- 手順がうまくいかないのは、あなたの間違いとは限りません。この手順に不備があるのかもしれません。[A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) のフォームに、画面に出た表示を書いてください。質問は [Discussions](https://github.com/atasino/CreateCodeBox/discussions) に書いてください。

## よくあるつまずき

この表の行のうち、私たちが自分で見たのは一部だけです。残りは、一般的な知識から書いたもので、あなたのパソコンでは違う表示になるかもしれません。画面に出ている表示を、左の列から探してください。3 列目に書いてあることをやってみます。それでも直らないときは、いちばん右の列のフォームを使ってください。コマンドは、すべて Git Bash で打ちます。

| 画面に出る表示 | 起きていること | 直し方 | それでも直らないとき |
|---|---|---|---|
| `claude: command not found`（Git Bash では `bash: claude: command not found`） | Claude Code が入っていないか、入れる前に開いた Git Bash のウィンドウを使っているようです。 | Git Bash を閉じて、新しいウィンドウを開き、`claude --version` と打ちます。それでも出るなら、手順 4 をやり直します。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `git: command not found` | Git for Windows が入っていないか、Git Bash の外で打っているようです。 | スタートメニューから Git Bash を開きます。Git Bash が無いときは、手順 1 をやり直します。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `CreateCodeBox は Python 3.8 以上が必要です。python.org から入れて、ターミナルを開き直してください。` と出ます。英語の 1 行も並んで出ます。`Python was not found` と出ることもあります。 | Python 3.8 以上が入っていないようです。 | 手順 2 をやり直し、「Add python.exe to PATH」にチェックを入れます。新しい Git Bash のウィンドウを開いて、`python --version` と打ちます。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `bash: ws/bin/ws.sh: No such file or directory` | `CreateCodeBox` のフォルダの中にいないようです。 | `cd ~/CreateCodeBox` と打ってから、もう一度同じコマンドを打ちます。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| 「Do you trust the files in this folder?」で No と答えた。表示は版によって違うことがあります。 | 信頼しないと、Claude Code は、ワークスペースの自動チェックを動かさないことがあります。私たちは、ワークスペースの許可の一覧が無視されるのを見ました。 | `CreateCodeBox` のフォルダで、もう一度 `claude` と打ち、yes と答えます。yes と答えるのは、この手順で用意したフォルダのときだけです。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `[CreateCodeBox` で始まる行が無い、またはワークスペースの自動チェック（hook）が動いていないと Claude が言う | ワークスペースの自動チェックが始まっていないようです。考えられる原因は 3 つのどれかです。信頼の質問に No と答えた、Python が無い、別のフォルダで `claude` を起動した、のいずれかです。 | `/exit` と打ち、`cd ~/CreateCodeBox` と `claude` を打ちます。また出るなら、`bash ws/bin/ws.sh doctor` を打ち、`NG` の付いた行を読みます。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `place: warn` と、そのあとに理由 | フォルダが、問題の起きやすい場所にあります。これは警告で、止まりはしません。 | フォルダを `%USERPROFILE%\CreateCodeBox` に移します。エクスプローラーで、ユーザーフォルダにドラッグして、名前を変えます。そのあと、そこで `claude` を起動します。そのまま進めてもかまいません。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| Claude Code が、何度も許可を求めてくる | Claude Code は、多くの操作の前に聞いてきます。こうなることがあります。 | 質問を 1 つずつ読みます。分かったものにだけ yes と答えます。分からないものは、Claude に意味を聞きます。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| アプリがブラウザで開かない | ファイルが、自動では開かなかったか、テキストエディタで開いたのかもしれません。 | エクスプローラーで、ユーザーフォルダの中の `CreateCodeBox\projects\<名前>\src` を開きます。`index.html` を右クリックして、「プログラムから開く」でブラウザを選びます。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |

`<名前>` は、`projects/` の中にある、あなたのアプリのフォルダの名前です。
