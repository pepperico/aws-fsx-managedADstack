# 画像ファイル置き場

このディレクトリは、プロジェクトのREADME.mdで使用する画像ファイルを格納する場所です。

## 使用方法

1. スクリーンショットやアーキテクチャ図などの画像ファイルをこのディレクトリに配置
2. README.mdから相対パスで参照

```markdown
![アーキテクチャ図](docs/images/architecture.png)
![デプロイメントフロー](docs/images/deployment-flow.png)
```

## 推奨ファイル形式

- **PNG**: スクリーンショット、図表
- **JPG/JPEG**: 写真
- **SVG**: ベクター図形（アーキテクチャ図など）

## ファイル命名規則

- 英数字とハイフンを使用
- わかりやすい名前を付ける
- 例：
  - `architecture-overview.png`
  - `fsx-setup-screen.png`
  - `deployment-phase1.png`

## 注意事項

- 大きすぎる画像ファイル（5MB以上）は避ける
- 機密情報が含まれる画像は配置しない
- 不要になった画像ファイルは定期的に削除する