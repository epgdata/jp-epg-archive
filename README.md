# jp-epg-archive

epgdata.jpで公開している過去の番組表を、地域・月ごとのファイルで配布しています。

このリポジトリには索引（`manifest.json`と`<地域>/manifest.json`）だけを置いています。ファイル本体は`https://archive.epgdata.jp/`（実体はCloudflare R2）からダウンロードしてください。同じURLをブラウザで開くと、ファイルの一覧が表示されます。

| 地域 | 番組表 | 索引 | 対象 |
|---|---|---|---|
| 東京（`tokyo`） | [tokyo.epgdata.jp](https://tokyo.epgdata.jp/) | [`tokyo/manifest.json`](tokyo/manifest.json) | 2025年1月以降の地上波（ＮＨＫ総合・Ｅテレ・日テレ・ＴＢＳ・フジテレビ・テレビ朝日・テレ東・ＴＯＫＹＯ ＭＸ・tvk・テレ玉・チバテレ）とBS |

地域は今後増えることがあります。配布している地域は、`manifest.json`の`regions`に載っているものです（残念ながら、今はまだ東京しかありません。将来的な拡張に備えて記載しています）。

## 更新方法

- 月末の放送から3日が経過した月を、その翌日以降に追加します。
- 月末の放送から14日が経過したところで、データベースと再突合し、さらに更新することがあります。

## ファイル

地域・月ごとに次のファイルを公開しています。

| 形式 | ファイル | 内容 |
|---|---|---|
| SQLite | `<地域>/YYYY/epg-<地域>-YYYY-MM.rN.sqlite.zst` | zstdで圧縮したSQLite。サイトと同じ正規化した表 |
| CSV | `<地域>/YYYY/epg-<地域>-YYYY-MM.rN.csv.zip` | `programmes.csv`と`aired.csv`（UTF-8、見出し行付き） |
| Parquet | `<地域>/YYYY/epg-<地域>-YYYY-MM.rN.programmes.parquet` | `programmes`表（zstd圧縮） |
| Parquet | `<地域>/YYYY/epg-<地域>-YYYY-MM.rN.aired.parquet` | `aired`表（zstd圧縮）。受信実績のある月だけ |

### 時刻と放送日

- 時刻（`start_time`）は日本時間で、`YYYY-MM-DD HH:MM:SS`の形です。
- 放送日（`broadcast_day`）は4:00から翌日4:00（30:00）までです。ファイルは放送日で月に分けています。

### programmes（EPGの予定）

放送局が送信するEPG（番組表の予定）です。

サブチャンネル（ＮＨＫ総合２、ＢＳ朝日２など）が親局と同じ番組を放送している時間の行は、CSVとParquetには入れていません（この行は番組名を持たず、親局の番組を指すだけであるためです）。
こうした行は全行のおよそ半分にあたります。SQLiteの`event`表にはEPGのとおりすべての行があり、`simulcast_of`に親局の`sid`が入っています。サブチャンネルが独自の番組を放送している行は、CSVとParquetにも入っています。

| 列 | 内容 |
|---|---|
| `broadcast_day`, `start_time`, `duration_sec` | 放送日、開始時刻、長さ（秒） |
| `onid`, `tsid`, `sid` | ARIBのoriginal_network_id、transport_stream_id、service_id |
| `service_name`, `band` | 局名、`terrestrial`か`bs` |
| `eid` | イベントID。日をまたぐと再利用されるので、局・放送日・開始時刻と組み合わせて使う |
| `title`, `subtitle`, `detail` | 番組名、概要、詳細（`- 見出し`の行で節を区切る） |
| `genre`, `video`, `audio` | ジャンル・映像・音声の属性（JSON） |
| `simulcast_of` | サブチャンネルが親局と同じ番組を放送しているとき、親局の`sid` |
| `free_ca` | 1なら有料放送 |
| `relay_onid`ほか | 別の局の番組へ引き継ぐときの引き継ぎ先 |

### aired（受信実績）

実際に受信した放送の記録です。例として、雨天中止の野球中継の代わりに放送された番組や、延長による繰り下げなど、`programmes`にないデータを含みます。
現在は東京23区で受信した2026年9月23日以降のＮＨＫ総合・Ｅテレ・日テレ・ＴＢＳ・フジテレビ・テレビ朝日・テレ東・ＮＨＫ ＢＳの実績を公開しています。
記録のない月の`aired.parquet`は公開しておらず、CSVの`aired.csv`は見出し行だけを記録しています。

| 列 | 内容 |
|---|---|
| `broadcast_day`, `start_time`, `duration_sec` | 実際に放送された時刻と長さ |
| `onid`, `tsid`, `sid`, `service_name`, `band`, `eid` | `programmes`と同じ |
| `title`, `detail` | 放送時点の番組名と説明 |
| `simulcast_of` | `programmes`と同じ |

### SQLiteの表

`service`, `attr`, `event`, `day_source`, `aired`の5表です。`event`の`genre_id`などは`attr`の`id`を指します。`day_source`には、局・放送日・時間帯ごとに、どの時点のEPGから取得したかを記録しています。

## 索引

`manifest.json`は地域の一覧です。（残念ながら、今はまだ東京しかありません。将来的な拡張に備えて記載しています）

```json
{
  "format_version": 1,
  "base_url": "https://archive.epgdata.jp/",
  "regions": [
    {"region": "tokyo", "name": "東京", "site": "https://tokyo.epgdata.jp/",
     "manifest": "tokyo/manifest.json"}
  ]
}
```

`<地域>/manifest.json`は、その地域のファイルの一覧です。

```json
{
  "format_version": 1,
  "region": "tokyo",
  "name": "東京",
  "site": "https://tokyo.epgdata.jp/",
  "base_url": "https://archive.epgdata.jp/",
  "months": [
    {"month": "2026-08", "revision": 1, "generated_at": "…", "rows": {"event": 73710, "…": 0},
     "files": [{"format": "csv+zip", "path": "tokyo/2026/epg-tokyo-2026-08.r1.csv.zip",
                "bytes": 0, "sha256": "…"}]}
  ]
}
```

## 利用条件

- 番組名・説明などの番組情報の著作権は、各放送局などの権利者にあります。
- データは受信したEPGと受信記録をそのまま整形したもので、正確さは保証しません。

## お問い合わせ

ファイル形式の改善、データの追加などを大歓迎します。Issueを立てていただくか、以下からお問い合わせください。

[tokyo.epgdata.jp お問い合わせ](https://tokyo.epgdata.jp/contact/)
