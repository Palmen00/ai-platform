param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$DocumentNames
)

$args = @(".\scripts\eval\prototype_gliner_compare.py")
if ($DocumentNames) {
    $args += $DocumentNames
}

py -3 @args
