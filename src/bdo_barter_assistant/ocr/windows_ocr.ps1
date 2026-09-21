param(
    [string[]]$ImagePath,
    [string]$ImageDirectory,
    [string]$Language = "ko",
    [string]$OutputPath
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.Runtime.WindowsRuntime

$null = [Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Storage.FileAccessMode, Windows.Storage, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.BitmapDecoder, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Graphics.Imaging.SoftwareBitmap, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Media.Ocr.OcrResult, Windows.Foundation, ContentType = WindowsRuntime]
$null = [Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime]

function Wait-WinRtOperation {
    param(
        [Parameter(Mandatory = $true)]$Operation,
        [Parameter(Mandatory = $true)][Type]$ResultType
    )

    $asTask = [System.WindowsRuntimeSystemExtensions].GetMethods() |
        Where-Object {
            $_.Name -eq "AsTask" -and
            $_.IsGenericMethod -and
            $_.GetParameters().Count -eq 1
        } |
        Select-Object -First 1
    $task = $asTask.MakeGenericMethod($ResultType).Invoke($null, @($Operation))
    $task.Wait()
    return $task.Result
}

$recognizerLanguage = New-Object Windows.Globalization.Language($Language)
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($recognizerLanguage)
if ($null -eq $engine) {
    throw "Windows OCR language is unavailable: $Language"
}

if ($ImageDirectory) {
    $ImagePath = @(
        Get-ChildItem -LiteralPath $ImageDirectory -Filter "*.png" -File |
            Sort-Object Name |
            ForEach-Object { $_.FullName }
    )
}
if (-not $ImagePath) {
    throw "Provide ImagePath or ImageDirectory."
}

$results = foreach ($path in $ImagePath) {
    $resolvedPath = (Resolve-Path -LiteralPath $path).Path
    $storageFile = Wait-WinRtOperation `
        ([Windows.Storage.StorageFile]::GetFileFromPathAsync($resolvedPath)) `
        ([Windows.Storage.StorageFile])
    $stream = Wait-WinRtOperation `
        ($storageFile.OpenAsync([Windows.Storage.FileAccessMode]::Read)) `
        ([Windows.Storage.Streams.IRandomAccessStream])
    try {
        $decoder = Wait-WinRtOperation `
            ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) `
            ([Windows.Graphics.Imaging.BitmapDecoder])
        $bitmap = Wait-WinRtOperation `
            ($decoder.GetSoftwareBitmapAsync()) `
            ([Windows.Graphics.Imaging.SoftwareBitmap])
        try {
            $ocrResult = Wait-WinRtOperation `
                ($engine.RecognizeAsync($bitmap)) `
                ([Windows.Media.Ocr.OcrResult])
            [PSCustomObject]@{
                path = $resolvedPath
                text = $ocrResult.Text
                lines = @($ocrResult.Lines | ForEach-Object { $_.Text })
            }
        }
        finally {
            if ($null -ne $bitmap) {
                $bitmap.Dispose()
            }
        }
    }
    finally {
        $stream.Dispose()
    }
}

$json = ConvertTo-Json -InputObject @($results) -Depth 4 -Compress
if ($OutputPath) {
    $utf8WithoutBom = New-Object System.Text.UTF8Encoding($false)
    [System.IO.File]::WriteAllText($OutputPath, $json, $utf8WithoutBom)
}
else {
    $json
}
