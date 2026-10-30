#requires -Version 7.0
param([Parameter(Mandatory)][string]$Output)
$ErrorActionPreference='Stop'
. (Join-Path $PSScriptRoot '../scripts/windows/guard_common.ps1')
New-Item -ItemType Directory -Path $Output -ErrorAction Stop | Out-Null
$testRoot=(Resolve-Path -LiteralPath $Output).Path

class GuardFakeProcess {
    [bool]$HasExited=$false
    [int]$ExitCode=0
    [int]$Id=1234
    [int]$Calls=0
    [IO.StringReader]$StandardOutput=[IO.StringReader]::new('test stdout')
    [IO.StringReader]$StandardError=[IO.StringReader]::new('test stderr')
    [bool]WaitForExit([int]$milliseconds) {
        $this.Calls++
        if($this.Calls -gt 1) { $this.HasExited=$true }
        return $this.HasExited
    }
}
function Assert($Condition, $Message) { if(-not $Condition) { throw $Message } }
# Test doubles avoid WSL, actual memory allocation and actual five-second waits.
function Start-Sleep { param($Seconds) }
function Get-GuardFreeGiB {
    $value=$script:samples[$script:sampleIndex]; $script:sampleIndex++
    if($value -eq 'error') { throw 'CIM test failure' }
    return [double]$value
}
function Resolve-GuardWslPath { param($Repository,$Distribution) $script:resolved++; return '/test repository' }
function Start-GuardWslProcess {
    param($Distribution,$LinuxRepository,$Command)
    $script:launched++
    if($script:launchFailure) { throw 'Launch test failure' }
    $fake=[GuardFakeProcess]::new(); $fake.ExitCode=$script:childCode; return $fake
}
$cases=@(
    @{name='first_low';samples=@(6);expected=1;launch=0},
    @{name='second_low';samples=@(10,6);expected=1;launch=0},
    @{name='invalid';samples=@([double]::NaN);expected=1;launch=0},
    @{name='success';samples=@(10,10,10);expected=0;launch=1},
    @{name='child_failed';samples=@(10,10,10);expected=2;launch=1;child=2},
    @{name='preventive';samples=@(10,10,4.9);expected=1;launch=1},
    @{name='monitor_failed';samples=@(10,10,'error');expected=1;launch=1},
    @{name='launch_failed';samples=@(10,10);expected=1;launch=1;fail=$true}
)
foreach($case in $cases) {
    $script:samples=$case.samples; $script:sampleIndex=0; $script:launched=0; $script:resolved=0
    $script:childCode=if($case.ContainsKey('child')){$case.child}else{0}
    $script:launchFailure=$case.fail
    $code=Invoke-GuardedWsl -Repository $testRoot -RunName $case.name -Minimum 7 -Command 'test argv'
    Assert ($code -eq $case.expected) "Unexpected exit: $($case.name): $code"
    Assert ($script:launched -eq $case.launch) "Unexpected launch: $($case.name)"
    if($case.launch -eq 0) { Assert ($script:resolved -eq 0) 'WSL started before admission' }
    $record=Get-Content -LiteralPath (Join-Path $testRoot "results/$($case.name)/supervisor.json") -Raw | ConvertFrom-Json
    Assert ($record.exit_code -eq $case.expected) 'Missing supervisor result'
    if($case.name -eq 'preventive') { Assert (Test-Path -LiteralPath (Join-Path $testRoot 'results/preventive/STOP_REQUESTED')) 'Missing preventive stop' }
    if($case.name -eq 'success') {
        $feed=Get-Content -LiteralPath (Join-Path $testRoot 'results/success/host_memory.json') -Raw | ConvertFrom-Json
        Assert ($feed.history.Count -eq 3) 'Memory history lost'
        Assert ((Get-Content -LiteralPath (Join-Path $testRoot 'results/success/supervisor.stdout.log') -Raw) -eq 'test stdout') 'Lost stdout'
    }
}
$preserved=Join-Path $testRoot 'results/success/supervisor.json'
$before=(Get-FileHash -LiteralPath $preserved).Hash
$rejected=$false
try { Invoke-GuardedWsl -Repository $testRoot -RunName success -Minimum 7 -Command 'test' } catch { $rejected=$true }
Assert $rejected 'Existing evidence was reused'
Assert ((Get-FileHash -LiteralPath $preserved).Hash -eq $before) 'Existing evidence changed'
foreach($file in Get-ChildItem (Join-Path $PSScriptRoot '../scripts/windows') -Filter '*.ps1') {
    $tokens=$null; $parseErrors=$null
    [Management.Automation.Language.Parser]::ParseFile($file.FullName,[ref]$tokens,[ref]$parseErrors) | Out-Null
    Assert ($parseErrors.Count -eq 0) "PowerShell syntax error: $file"
}
@{passed=$true;cases=$cases.Count;evidence_preserved=$true} | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $testRoot 'summary.json')
Write-Output 'Windows supervisor contracts passed'
