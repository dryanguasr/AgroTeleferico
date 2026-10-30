#requires -Version 7.0
# Shared Windows host admission and WSL monitoring. Dot-source; no work on import.
function Get-GuardFreeGiB {
    return (Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB
}

function Write-GuardMemorySample($MemoryFile, $History) {
    $free=Get-GuardFreeGiB
    if([double]::IsNaN($free) -or [double]::IsInfinity($free) -or $free -lt 0) { throw 'Invalid host memory sample' }
    $now=[DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()/1000.0
    $History.Add(@{unix_s=$now;free_gib=$free})
    while($History.Count -gt 0 -and $History[0].unix_s -lt $now-15) { $History.RemoveAt(0) }
    @{unix_s=$now;free_gib=$free;history=@($History.ToArray())} |
        ConvertTo-Json -Depth 4 -Compress | Set-Content -LiteralPath ($MemoryFile+'.tmp') -Encoding utf8
    Move-Item -LiteralPath ($MemoryFile+'.tmp') -Destination $MemoryFile -Force
    return $free
}

function Resolve-GuardWslPath($Repository, $Distribution) {
    $path=(& wsl.exe -d $Distribution -- wslpath -a $Repository).Trim()
    if($LASTEXITCODE -ne 0 -or -not $path.StartsWith('/')) { throw 'Cannot resolve repository inside WSL' }
    return $path
}

function Start-GuardWslProcess($Distribution, $LinuxRepository, $Command) {
    $info=[Diagnostics.ProcessStartInfo]::new()
    $info.FileName='wsl.exe'; $info.UseShellExecute=$false; $info.CreateNoWindow=$true
    $info.RedirectStandardOutput=$true; $info.RedirectStandardError=$true
    foreach($arg in @('-d',$Distribution,'--cd',$LinuxRepository,'--','bash','-lc',$Command)) { $info.ArgumentList.Add($arg) }
    return [Diagnostics.Process]::Start($info)
}

function Invoke-GuardedWsl {
    param(
        [Parameter(Mandatory)][string]$Repository,
        [Parameter(Mandatory)][ValidatePattern('^[a-z0-9_]+$')][string]$RunName,
        [Parameter(Mandatory)][ValidateSet(6,7,7.5,8,9,10,14)][double]$Minimum,
        [Parameter(Mandatory)][string]$Command,
        [string]$Distribution='Ubuntu-24.04',
        [hashtable]$Metadata=@{}
    )
    $ErrorActionPreference='Stop'
    $runRoot=Join-Path $Repository ('results/'+$RunName)
    if(Test-Path -LiteralPath $runRoot) { throw 'Output already exists; preserve previous evidence' }
    New-Item -ItemType Directory -Path $runRoot | Out-Null
    $memoryFile=Join-Path $runRoot 'host_memory.json'
    $history=[Collections.Generic.List[object]]::new()
    $admission=@{first_free_gib=$null;second_free_gib=$null;minimum_gib=$Minimum;reserve_gib=4;admitted=$false}
    $proc=$null; $code=1; $failure=$null; $phase='admission'; $stdout=$null; $stderr=$null
    try {
        $admission | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'admission.json')
        $admission.first_free_gib=Write-GuardMemorySample $memoryFile $history
        $admission | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'admission.json')
        if($admission.first_free_gib -lt $Minimum) { throw "Admission requires $Minimum GiB free" }
        Start-Sleep -Seconds 5
        $admission.second_free_gib=Write-GuardMemorySample $memoryFile $history
        $admission.separation_s=5
        $admission.admitted=$admission.second_free_gib -ge $Minimum
        $admission | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'admission.json')
        if(-not $admission.admitted) { throw 'Second admission sample below minimum' }
        $phase='launch'
        $linuxRepository=Resolve-GuardWslPath $Repository $Distribution
        $proc=Start-GuardWslProcess $Distribution $linuxRepository $Command
        $stdout=$proc.StandardOutput.ReadToEndAsync(); $stderr=$proc.StandardError.ReadToEndAsync()
        $phase='monitor'
        while(-not $proc.WaitForExit(1000)) {
            $free=Write-GuardMemorySample $memoryFile $history
            if($free -lt 5) { Set-Content -LiteralPath (Join-Path $runRoot 'STOP_REQUESTED') 'Preventive stop below 5 GiB to preserve 4 GiB reserve' }
            if(Test-Path -LiteralPath (Join-Path $runRoot 'STOP_REQUESTED')) { throw 'Preventive or explicit stop requested' }
        }
        $code=$proc.ExitCode
        # A preventive stop is a failed run even if the child exits zero.
        if(Test-Path -LiteralPath (Join-Path $runRoot 'STOP_REQUESTED')) { $code=1 }
        $phase='completed'
    } catch {
        $failure=$_.ToString(); $code=1
        if($null -ne $proc -and -not $proc.HasExited) {
            Set-Content -LiteralPath (Join-Path $runRoot 'STOP_REQUESTED') $failure
            if(-not $proc.WaitForExit(55000)) { $failure+='; child still running: inspect recorded PID for scoped cleanup' }
        }
    } finally {
        if($null -ne $proc -and $proc.HasExited) {
            if($null -ne $stdout) { [IO.File]::WriteAllText((Join-Path $runRoot 'supervisor.stdout.log'),$stdout.GetAwaiter().GetResult()) }
            if($null -ne $stderr) { [IO.File]::WriteAllText((Join-Path $runRoot 'supervisor.stderr.log'),$stderr.GetAwaiter().GetResult()) }
        }
        $record=@{schema='agro-windows-supervisor-v1';exit_code=$code;monitoring_error=$failure;phase=$phase;
                  pid=$(if($null -ne $proc){$proc.Id}else{$null});
                  child_exited=$(if($null -ne $proc){$proc.HasExited}else{$null})}
        foreach($key in $Metadata.Keys) { $record[$key]=$Metadata[$key] }
        $record | ConvertTo-Json | Set-Content -LiteralPath (Join-Path $runRoot 'supervisor.json')
    }
    Write-Host "Guard completed: exit=$code; evidence=$runRoot"
    return $code
}
