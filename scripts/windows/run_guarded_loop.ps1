#requires -Version 7.0
param(
    [Parameter(Mandatory)][ValidatePattern('^[a-z0-9_]+$')][string]$RunName,
    [ValidateSet('hybrid_gust','central_gust','hybrid_calm','hybrid_half_dt','hybrid_half_shape','capture')][string]$Case='hybrid_gust',
    [ValidateSet('overview','lower','upper')][string]$View='overview',
    [ValidateRange(1,342)][double]$Until=341,
    [switch]$AllViews,
    [switch]$NoGui,
    [switch]$FollowCarrier,
    [ValidateSet('buitrago_patio','buitrago_entre_pisos','ladera_agricola')][string]$Scenario,
    [ValidateSet('baseline','compact_candidate','revised_supports')][string]$Variant='revised_supports',
    [string]$Distribution='Ubuntu-24.04'
)
$ErrorActionPreference='Stop'
$repository=[IO.Path]::GetFullPath((Join-Path $PSScriptRoot '../..'))
. (Join-Path $PSScriptRoot 'guard_common.ps1')
$minimum=if($Case -eq 'capture'){if($NoGui){10}else{14}}else{9}
$command='source /opt/ros/jazzy/setup.bash && source install/setup.bash && exec python3 '
if ($Case -eq 'capture') {
    $command+='scripts/capture_loop.py --output results/'+$RunName+'/capture --host-memory results/'+$RunName+'/host_memory.json --video --timeout 1800 --view '+$View+' --until '+$Until.ToString([Globalization.CultureInfo]::InvariantCulture)
    if(-not $NoGui) { $command+=' --gui' }
    if($FollowCarrier) { $command+=' --follow-carrier 0' }
    if($AllViews) { $command+=' --all-views' }
} else {
    $command+='scripts/run_loop_guarded.py --output results/'+$RunName+'/'+$Case+' --host-memory results/'+$RunName+'/host_memory.json --case '+$Case
}
if($Scenario) { $command+=' --scenario '+$Scenario+' --variant '+$Variant }
$code=Invoke-GuardedWsl -Repository $repository -RunName $RunName -Minimum $minimum -Command $command -Distribution $Distribution
exit $code
