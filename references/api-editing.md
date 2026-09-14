# Resolve 21.1 APIによる編集

2026-09-15にネイティブMCPが返した `DaVinciResolveScript.pyi` と開発者ドキュメントに基づく。読み取りで確認したホストは21.1.0.17。以下の編集例はライブプロジェクトで実行済みの保証ではない。実行時の定義と実際の結果を照合する。

## 定義の取得

`get_scripting_api(types=[...])` の共通型は `MediaPool`, `Timeline`, `TimelineItem`, `AppendClipInfo`, `ImportClipInfo`。速度は `SpeedOptions`、トランジションは `TransitionOptions`, `FadeInfo`、字幕は `AutoCaptionSettings`、出力は `RenderSettings`, `RenderJobStatus`。

21.1の正規形は `TimelineItem.GetProperties()/SetProperties(dict)`、`Timeline.GetSettings()/SetSettings(dict)`、`Project.GetSettings()/SetSettings(dict)`。`MediaPoolItem.GetClipProperty()` は単数形のまま。旧例の `SetProperty("Speed", ...)` を使わない。

Python変数がMCP呼び出し間で保持されると仮定せず、毎回対象をIDで取り直す。オブジェクトそのものを返さず、ID・名前・数値を `result` に詰める。

## 新規タイムラインのカット・トリム

1. 対象ファイルの存在をOS側で調べる。絶対パスをPythonリテラルへ安全にシリアライズする。文字列連結でシェルを組み立てない。
2. `media_pool.ImportMedia([{"FilePath": absolute_path}])` を呼ぶ。戻った項目の `GetClipProperty()` で `File Path`, `FPS`, `Frames`, `Start`, `Start TC`, `Audio Ch`, `Resolution` を確認する。音声の有無や順序をファイル名だけで推測しない。
3. 別名の `CreateEmptyTimeline(name)` を作り、素材を置く前に設定を確認する。必要な `SetSettings({...})` は成功と `GetSettings()` の値を確かめる。
4. `project.SetCurrentTimeline(timeline)` を確認し、範囲を指定して配置する。

```python
# 各変数は調査と編集指示から求める。素材fpsとタイムラインfpsが同じ例。
spec = {
    "mediaPoolItem": media_item,
    "startFrame": source_in,
    "endFrame": source_out_exclusive - 1,
    "recordFrame": timeline.GetStartFrame() + timeline_offset,
}
items = media_pool.AppendToTimeline([spec])
if not items:
    raise RuntimeError("AppendToTimeline failed; inspect before retry")
result = [{"id": x.GetUniqueId(), "start": x.GetStart(),
           "end": x.GetEnd(), "duration": x.GetDuration()} for x in items]
```

編集計画の終了はexclusive、Append例の終了はinclusiveとして変換する。ただしスタブは終端包含と素材開始オフセットを十分に定義していない。最初の意図した短い区間で `GetSourceStartFrame/EndFrame`, `GetDuration`, `GetStart/End` とビューアーの先頭・末尾を照合し、その素材の対応を確定してから一括配置する。

`recordFrame` はタイムライン絶対フレーム。既定開始が01:00:00:00でもゼロを渡さない。ソース範囲には素材fps、配置にはタイムラインfpsを使う。混在fpsは時間換算と実際の挿入尺で次の位置を決める。VFR素材を固定fpsとみなして精密編集しない。

`mediaType` 省略時は挿入された映像・音声の両方を確認する。1は映像のみ、2は音声のみ。`trackIndex` は1起点で、対象種別のトラックを事前確認する。映像/音声を別々に入れた場合は素材範囲と配置を合わせ、必要な組だけ `SetClipsLinked(items, True)` でリンクする。

グレード、Fusion、リタイム等を持つ既存クリップを削除・再挿入してトリムしない。分割・トリムは [ui-editing.md](ui-editing.md) のEditページ経路へ。`DeleteClips(items, rippleDelete=...)` は削除APIであり、分割APIではない。意図した削除でも関連トラックへのリップル影響を確認する。

## 一定速度・静止

対象IDを照合し、元の `GetSpeed()`、開始・終了、リンク項目を記録する。

```python
ok = item.SetSpeed({
    "Percentage": 200.0,
    "RippleTimeline": True,
    "PitchCorrection": True,
    "StretchKeyframesToFit": False,
})
if not ok:
    raise RuntimeError("SetSpeed failed; inspect before retry")
result = {"speed": item.GetSpeed(), "start": item.GetStart(),
          "end": item.GetEnd(), "duration": item.GetDuration()}
```

200%は2倍速、50%は半速、0%はフリーズ。`RippleTimeline` は後続を移動させる編集かどうかで選ぶ。固定配置ならFalseにし、変更後のソース範囲・尺・隙間を確認する。固定ソース範囲を保って尺も変える場合は、おおよそ `ソース秒数 / (Percentage / 100)` の秒数になるか確認する。0%は静止フレーム位置と表示尺を別に決める。

全リンク項目が望む速度・尺になったか読み取りと再生で確認し、リンク音声に無条件で処理を二重適用しない。負値による逆再生はスタブに明示されていないため、受理されると決めつけずUIで設定・検証する。

`SetProperties` の `RetimeProcess` は補間方式、`MotionEstimation` は動き推定。実行時の定数を使い、速度カーブの代わりにしない。滑らかな可変速度はUI参照へ。

## 映像・音声トランジション

秒指定はタイムラインfpsで最寄りの整数フレームへ丸め、実際の尺を記録する。例: 24000/1001fpsで0.5秒は12フレーム（0.5005秒）。素材fpsとタイムラインfpsが違う場合、素材fpsでトランジション尺を計算しない。

隣接A/Bのトラック・境界を確認する。中心配置にはAのアウト後とBのイン前に各側の必要な余裕フレームが要る。奇数尺、リタイム、逆再生では実際の消費範囲を確認する。

```python
transition = outgoing_item.AddTransition({
    "type": "Cross Dissolve", "category": "simple",
    "position": "end", "alignment": "center", "duration": 12,
})
if transition is None:
    raise RuntimeError("Transition not added; inspect handles and neighbors")
result = {"id": transition.GetUniqueId(), "type": transition.GetType(),
          "start": transition.GetStart(), "end": transition.GetEnd(),
          "duration": transition.GetDuration()}
```

`position` は `start/end`、`alignment` は `left/center/right`。上はA末尾に1回だけ付ける例で、B先頭へ重複適用しない。単独端は黒へのフェードになり得るため、中央でAとBが混ざることをプレビューする。ハンドル不足時に勝手に静止フレームや尺変更で埋めない。指定内で解決できなければ不足量と代案を相談する。

音声には `category="audio"` が使える。音声 `type` の一覧はスタブにないため、現行UI/公式資料で正確な名前を確認する。要求されたカーブ（一定ゲイン/一定パワー等）を保持する。

`SetFades({"FadeIn": frames, "FadeOut": frames})` と `GetFades()` は端のフェーダー。反対側の既存フェードを保持するなら取得値に変更をマージする。クロスフェードの代替では、別トラックのA/Bが実際に同じ区間で重なるように配置してからAのFadeOutとBのFadeInを設定する。同期と全体尺を保ち、2重音声や音量の谷・ピークがないか聴く。カーブが要求に合わなければUIの音声トランジションを使う。

## 自動字幕

カットと速度変更を確定後に実行する。21.1の `AutoCaptionSettings` の正規キーは文字列。

```python
ok = timeline.CreateSubtitlesFromAudio({
    "language": resolve.AUTO_CAPTION_JAPANESE,
    "charsPerLine": 20,
    "lineBreak": resolve.AUTO_CAPTION_LINE_DOUBLE,
    "gap": 0,
})
result = {"accepted": ok, "subtitle_tracks": timeline.GetTrackCount("subtitle")}
```

定数名を事前にスタブで照合する。20文字は日本語の初期案であり希望・画面に合わせる。charsPerLineは1〜60、gapは0〜10フレーム。完了と字幕イベント増加を確認し、音声に照らして固有名詞や時刻を修正する。失敗/タイムアウト時は既存字幕を調べてから対処する。

21.1スタブには手入力字幕イベントの作成/テキスト設定/SRT配置APIはない。`ImportIntoTimeline` はAAF用、`ImportTimelineFromFile` にもSRTは列挙されていない。SRTを渡せば動くと仮定しない。`InsertTitleIntoTimeline` やFusion Text+は字幕トラックとは別物。指定字幕はUI参照へ。

## 書き出し

`GetRenderFormats`, `GetRenderCodecs(format)` 等で対応を照会し、`SetCurrentRenderFormatAndCodec` の成功を確認する。完成動画全体は通常 `SetCurrentRenderMode(1)`（Single clip）。設定変更前の状態を記録する。

`SetRenderSettings` の代表キー:

- `TargetDir`, `CustomName`, `SelectAllFrames`, `ExportVideo`, `ExportAudio`。
- `ReplaceExistingFilesInPlace=False`, `UseUniqueFilenames=True` で意図しない上書きを避ける。
- `ExportSubtitle=True`, `SubtitleFormat="BurnIn" / "SeparateFile" / "EmbeddedCaptions"`。コンテナ対応・字幕トラック選択・UI表示を確認し、勝手に形式を固定しない。

限定範囲では `MarkIn/MarkOut` の座標と終端を確認する。`AddRenderJob()` のIDを保存し、`StartRendering([job_id])` でそのIDだけ開始する。短い呼び出しで `GetRenderJobStatus(job_id)` を確認する。長いMCP呼び出し内で完了待ちしない。`Complete` と出力ファイルの存在・サイズ・尺・解像度・音声・字幕を確認して完了を報告する。
