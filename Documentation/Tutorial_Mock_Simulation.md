# 模擬シミュレーション接続チュートリアル

simv・ライセンス・外部キューは不要です。小さなテキストファイルだけを作り、
ユーザーシステムのrunとcollectorをMockingbirdに接続する流れを体験します。
追加のソースcloneは行いません。

## 1. 準備

Mockingbirdのリポジトリ直下で実行します。インストール済みなら環境を有効化するだけです。

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
```

| ファイル | 担当 |
| --- | --- |
| `examples/sample-collector.yaml` | Jobと実行／回収コマンドの接続 |
| `examples/sample_run.py` | 模擬simv。ユーザー側のファイルを作る |
| `examples/sample_collect.py` | ファイルから判定し、artifact付きJSONを標準出力に返す |
| `examples/sample_finish.py` | 外部処理の完了と回収サービスの復旧を模擬する |

runもcollectorも、環境変数`MB_RUN_ID`と`MB_JOB_ID`で対象を特定します。
この例はargvではなく環境変数を使うため、YAMLの`args`は空です。

## 2. 計画して実行する

```sh
mb doctor examples/sample-collector.yaml
mb prepare examples/sample-collector.yaml
mb setup examples/sample-collector.yaml
mb plan examples/sample-collector.yaml
mb run examples/sample-collector.yaml
```

8件がリスト順に実行されます。表示された`run:`のパスの最後の部分をコピーします。
以下の例のIDは、自分の実行で表示された値に置き換えてください。

```sh
RUN_ID=20261007_140000_000000_sample-collector
RUN_DIR="runs/sample-collector/$RUN_ID"
```

## 3. ユーザー側の生成ファイルを見る

```sh
ls "work/sample-results/$RUN_ID/test_pass"
cat "work/sample-results/$RUN_ID/test_pass/result.txt"
cat "work/sample-results/$RUN_ID/test_fail/result.txt"
cat "work/sample-results/$RUN_ID/test_pass/sim.log"
```

各Jobに`result.txt`、`tarmac.log`、`wave.fsdb`、`sim.log`ができます。
すべて模擬テキストです。`wave.fsdb`は波形ビューアで開けるFSDBではありません。
完了したJobには`done`もあります。`test_pending`にはまだありません。

この時点ではユーザー側runはJSONを作っていません。`result.txt`は単なる
PASS／FAIL／ERROR／SKIPの文字列です。実行コマンド自体は全件終了コード0で戻ります。

## 4. 初回の結果回収

```sh
mb collect examples/sample-collector.yaml --run-dir "$RUN_DIR"
echo $?
mb status examples/sample-collector.yaml --run-dir "$RUN_DIR"
```

| Job | 初回の結果 | 意味 |
| --- | --- | --- |
| test_pass | PASS | 正常判定 |
| test_fail | FAIL | 模擬scoreboard不一致 |
| test_error | ERROR | 模擬simulator fatal。確定済みの判定 |
| test_skip | SKIP | 対象外の構成 |
| test_pending | PENDING | 完了待ち |
| test_collect_error | collection_error | collectorが終了コード7で異常終了 |
| test_bad_json | collection_error | collectorの出力が不正JSON |
| test_no_check | PASS | collectorを呼ばず、判定を省略 |

期待値は`total=8, pass=2, fail=1, error=1, skip=1, pending=1,
uncollected=0, collection_error=2`です。

未確定があるため全体はPENDING、collectの終了コードは **2** です。
意図した結果なので、コマンドを個別に実行して次へ進んでください。

JSONを作るのは`sample_collect.py`です。Mockingbirdはそれを受け取り、
Job別の回収記録とrun全体の`result.json`を保存します。
`artifacts`には上記4ファイルの絶対パスが入り、no-checkでは空になります。
Mockingbirdはartifact自体をコピーしません。

## 5. 外部完了・復旧後に、同じsetを再回収する

```sh
python3 examples/sample_finish.py "$RUN_ID"
mb collect examples/sample-collector.yaml --run-dir "$RUN_DIR"
echo $?
mb status examples/sample-collector.yaml --run-dir "$RUN_DIR"
```

finishはユーザー側の完了マーカーと障害マーカーだけを変更します。
Mockingbirdの記録には触れず、runも再実行しません。

PENDINGと2件の回収エラーがPASSになります。期待値は
`total=8, pass=5, fail=1, error=1, skip=1`で、未確定件数はすべて0です。
全件の回収は完了しますが、確定済みのFAIL／ERRORがあるため全体はFAIL、
終了コードは **1** です。最終ERRORは回収エラーと違い、再試行されません。

## 6. 確定済みのcollectorが再実行されないことを確認する

```sh
wc -l "work/sample-results/$RUN_ID"/*/collector_calls.txt
mb collect examples/sample-collector.yaml --run-dir "$RUN_DIR"
wc -l "work/sample-results/$RUN_ID"/*/collector_calls.txt
```

確定済みの4件は1行、復旧した3件は2行、no-checkは呼出し記録自体がありません。
3回目のcollectでは行数が変わりません。このファイルはチュートリアル用の計測です。

## 7. 実際のユーザーシステムへ置き換える

- `sample_run.py`のファイル作成を、実際のsimv実行や外部キューへの投入に置き換える。
- `sample_collect.py`の完了確認・判定処理を、実際の結果形式に合わせる。
- ログ・波形などの参照先を`artifacts`へ返す。
- `sample_finish.py`と障害マーカー・呼出し回数の計測は模擬体験用なので不要。

ファイルの場所、完了マーカー、判定方法はユーザー側の取り決めです。
Mockingbirdが要求する外部への返却形式はcollectorのJSONです。

別の判定を試すときは`mb run`で新しいrunを作ります。確定済みの結果は、
元ログを書き換えても再collectでは判定し直しません。各runのファイルは別々に残ります。
