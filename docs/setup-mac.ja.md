この文書は、英語版（正本）[setup-mac.md](setup-mac.md) の翻訳です。食い違いがあれば英語版が優先します。

# Mac での準備

状態: 以前の版（0.2.0）を macOS で試しました。このページ用の画面の写真は、まだ作っていません（`docs/img/README.md` を見てください）。

必要なものは 3 つです。Claude Code、`git`、Python 3 です。Python は 3.8 以上が必要で、私たちが試したのは 3.9 です。

## 1. ターミナルを開く

command キーとスペースキーを同時に押します。「ターミナル」と入力して、return キーを押します。文字が並んだウィンドウが開きます。ここにコマンドを打ち、1 つ打つたびに return キーを押します。

## 2. git と Python を確かめる

次の 2 行を、1 行ずつ打ちます。

```
git --version
python3 --version
```

- どちらの行にもバージョンの数字が出たら、手順 3 へ進みます。Python は、バージョンが 3.8 以上であることが必要です。
- Mac に、「コマンドライン・デベロッパ・ツール」（command line developer tools）を入れるかを聞くウィンドウが出たら、「インストール」（Install）を押します。終わるまで待ちます。これで `git` と Python 3 が入ります。そのあと、2 行をもう一度打ちます。

## 3. Claude Code を入れる

Anthropic の公式の案内（https://code.claude.com/docs/en/overview）に従ってください。サインインに必要なものと料金は、その案内に書いてあります。そのあと、動くかを確かめます。

```
claude --version
```

## 4. アプリ用のフォルダを作って始める

CreateCodeBox は、アプリ 1 つにつき、フォルダを 1 つ使います。空のフォルダを作り、そこで Claude Code を開いて、1 文を貼り付けます（[README](../README.ja.md) の手順 3）。Claude は、そのフォルダに CreateCodeBox を用意するよう指示してあります。この方法は、Mac で、Claude Code が許可を求めない設定にした試験でしか試していません。ふつうの設定では、まだ試していません。

先に、次の 3 行で、フォルダを作って Claude Code を開きます。ターミナルに 1 行ずつ打ち、1 行ごとに return キーを押します。

```
mkdir ~/coffee-log
cd ~/coffee-log
claude
```

1 行目は、ホームフォルダ（あなたのユーザー名のフォルダ）の中に、`coffee-log` という空のフォルダを作ります。名前は、あなたのアプリの名前に変えてください。使えるのは、英字・数字・`-` だけで、空白は入れません。2 行目で、そのフォルダに入ります。3 行目で、Claude Code を起動します。ユーザー名に空白や英語以外の文字が入っているときは、下の「フォルダを置く場所」を見てください。Visual Studio Code や Claude のアプリを使うときは、[README](../README.ja.md) の手順 2 を見てください。

Claude Code が、このフォルダを信頼してよいかを聞いてくることがあります。今作ったばかりの空のフォルダなので、yes と答えます。

そのあと、[README](../README.ja.md) の手順 3 の 1 文を、Claude Code に貼り付けます。Claude は、このフォルダに CreateCodeBox を用意するよう指示してあります。そのあとは、README の手順 4 に従います。Claude が、そのフォルダで Claude Code を開き直す方法を教えます。ほかのフォルダで Claude Code をもう開いているときも、そこに 1 文を貼り付けてかまいません。新しいフォルダを作るのを、Claude が手伝います。

**1 文でうまくいかないとき: 自分の手で用意します。** 先に、`/exit` と打って Claude Code を終了するか、2 つ目のターミナルのウィンドウを開きます。`cd ~/coffee-log`（フォルダの名前は、自分のものに変えます）で、新しく作った空のフォルダに入ります。そのあと、次の 2 行を、ターミナルに 1 行ずつ貼り付けます。1 行ごとに return キーを押します。

```
git clone https://github.com/atasino/CreateCodeBox.git .
claude
```

1 行目のアドレスは、このリポジトリのものです。別の人が用意した CreateCodeBox（GitHub 上のコードの置き場）を使うときは、1 行目の `https://` から `.git` までを、そのアドレスに置き換えてください。アドレスは、GitHub のページの緑の **Code** ボタンからコピーできます。ボタンを押して、コピーのアイコンを押します。1 行目は、今いるフォルダに、CreateCodeBox をダウンロードして置きます。最後の `.` は「今いるフォルダに置く」という意味で、置き先のフォルダは空でなければなりません。2 行目で、Claude Code を起動します。

`git clone` が、フォルダが空でないと表示したときは、別の新しい空のフォルダを作り、そこで同じ 2 行を打ってください。

Claude Code が、このフォルダを信頼してよいかを聞いてきたら、質問を読んでください。使ったアドレスから作ったフォルダで、そのアドレスを信頼できるなら、yes と答えます。

この 2 行のあとは、Claude Code が、あなたのアプリ用のフォルダで動いています。このウィンドウをそのまま使います。[README](../README.ja.md) の手順 4 は飛ばして、手順 5 に進み、作りたいアプリを Claude に伝えます。

## フォルダを置く場所

**おすすめ:** アプリごとに、新しい空のフォルダを 1 つ、ホームフォルダの直下に作ります。名前は、英字・数字・`-` だけで、空白は入れません。たとえば `~/coffee-log` です。このページで「アプリ用のフォルダ」と言うときは、このフォルダのことです。

**Mac のユーザー名に空白や、英語以外の文字が入っているとき:** フォルダを、ホームフォルダの中に置かないでください。代わりに、`/Users/Shared/` のすぐ下に置きます。たとえば `/Users/Shared/coffee-log` です。このパスには、英字だけが入っていて、空白はありません。ワークスペースは、ホームフォルダの外にあるフォルダのほとんどについて警告します。この場所については、警告しません。

**避ける場所:**

- **ダウンロード・デスクトップ・書類。** 同期のアプリが、これらのフォルダをクラウドにコピーすることがよくあります。作ったものや鍵のファイルが、パソコンの外に出てしまうかもしれません。ダウンロードしたファイルもここに入るので、外から来た `CLAUDE.md` ファイルが混ざるおそれもあります。
- **iCloud Drive・OneDrive・Dropbox が同期するフォルダ。** 作ったものがクラウドにコピーされるかもしれません。同期で、`.ws/` の中の記録が壊れることもあります。
- **ほかの Git のリポジトリの中。** Git が 2 つのプロジェクトを取り違えることがあります。外側のリポジトリの `CLAUDE.md` が読み込まれることもあります。
- **空白や、英語以外の文字を含むパス（ファイルの場所の書き方）。** そのようなパスで失敗するソフトやスクリプトがあります。
- **システムのフォルダ。** たとえば `/tmp` や `/usr`。作ったものが消されるかもしれません。管理者の権限が要ることもあります。

ワークスペースは、これを確かめます。`bash ws/bin/ws.sh doctor` を打ってください。`place: ok` か、理由つきの `place: warn` が出ます。警告は出しますが、止めはしません。

## 5. うまくいかないとき

- アプリ用のフォルダに入り（たとえば `cd ~/coffee-log`）、そこで `bash ws/bin/ws.sh doctor` を打ちます。確かめた項目ごとに 1 行が出ます。
- Claude Code が 1 ステップごとに許可を求めるのは、ふつうのことです。質問を読んで、答えてください。分からない質問に yes と答えないでください。意味は Claude に聞いてください。
- 鍵やパスワードを、チャットに貼り付けないでください。
- 手順がうまくいかないのは、あなたの間違いとは限りません。この手順に不備があるのかもしれません。[A step did not work](https://github.com/atasino/CreateCodeBox/issues/new/choose) のフォームに、画面に出た表示を書いてください。質問は [Discussions](https://github.com/atasino/CreateCodeBox/discussions) に書いてください。

## よくあるつまずき

この表の行のうち、私たちが自分で見たのは一部だけです。残りは、一般的な知識から書いたもので、あなたのパソコンでは違う表示になるかもしれません。画面に出ている表示を、左の列から探してください。3 列目に書いてあることをやってみます。それでも直らないときは、いちばん右の列のフォームを使ってください。

| 画面に出る表示 | 起きていること | 直し方 | それでも直らないとき |
|---|---|---|---|
| `claude: command not found`（ターミナルでは `zsh: command not found: claude`） | Claude Code が入っていないか、入れる前に開いたターミナルのウィンドウを使っているようです。 | ターミナルを閉じて、新しいウィンドウを開き、`claude --version` と打ちます。それでも出るなら、手順 3 をやり直します。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `git: command not found`、または `xcode-select: note: No developer tools were found`、または「コマンドライン・デベロッパ・ツール」のウィンドウ | `git` が、まだ入っていないようです。 | `xcode-select --install` と打ち、「インストール」を押して、終わるまで待ちます。そのあと `git --version` と打ちます。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `CreateCodeBox は Python 3.8 以上が必要です。python.org から入れて、ターミナルを開き直してください。` と出ます。英語の 1 行も並んで出ます。 | Python 3.8 以上が入っていないようです。 | https://www.python.org/downloads/ から Python 3 を入れ、新しいターミナルのウィンドウを開いて、`python3 --version` と打ちます。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `bash: ws/bin/ws.sh: No such file or directory` | アプリ用のフォルダの中にいないようです。 | `cd ~/coffee-log`（フォルダの名前は自分のものに変えます）と打ってから、もう一度同じコマンドを打ちます。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| 「Do you trust the files in this folder?」で No と答えた。表示は版によって違うことがあります。 | 信頼しないと、Claude Code は、ワークスペースの自動チェックを動かさないことがあります。私たちは、ワークスペースの許可の一覧が無視されるのを見ました。 | アプリ用のフォルダで、もう一度 `claude` と打ち、yes と答えます。yes と答えるのは、この手順で用意したフォルダのときだけです。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `[CreateCodeBox` で始まる行が無い、または ワークスペースの自動チェック（hook）が動いていないと Claude が言う | ワークスペースの自動チェックが始まっていないようです。考えられる原因は 3 つのどれかです。信頼の質問に No と答えた、Python が無い、別のフォルダで `claude` を起動した、のいずれかです。 | `/exit` と打ち、`cd ~/coffee-log`（フォルダの名前は自分のものに変えます）と `claude` を打ちます。また出るなら、`bash ws/bin/ws.sh doctor` を打ち、`NG` の付いた行を読みます。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| `place: warn` と、そのあとに理由 | フォルダが、問題の起きやすい場所にあります。これは警告で、止まりはしません。 | ホームフォルダの中に、アプリ用の新しい空のフォルダを作り（手順 4 を見てください）、そこで CreateCodeBox を用意し直します。これまでに作ったものは、古いフォルダに残ります。そのまま進めてもかまいません。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| Claude Code が、何度も許可を求めてくる | Claude Code は、多くの操作の前に聞いてきます。こうなることがあります。 | 質問を 1 つずつ読みます。分かったものにだけ yes と答えます。分からないものは、Claude に意味を聞きます。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |
| アプリがブラウザで開かない | ファイルが、自動では開かなかったのかもしれません。 | Finder で shift + command + H を押してホームフォルダに行き、アプリ用のフォルダ、`projects/<名前>/src` の順に開いて、`index.html` をダブルクリックします。 | [フォームを開く（A step did not work）](https://github.com/atasino/CreateCodeBox/issues/new/choose) |

`<名前>` は、`projects/` の中にある、あなたのアプリのフォルダの名前です。
