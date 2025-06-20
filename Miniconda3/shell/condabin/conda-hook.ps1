$Env:CONDA_EXE = "d:\Python\project\AI-Vtuber\Miniconda3\Scripts\conda.exe"
$Env:_CE_M = ""
$Env:_CE_CONDA = ""
$Env:_CONDA_ROOT = "d:\Python\project\AI-Vtuber\Miniconda3"
$Env:_CONDA_EXE = "d:\Python\project\AI-Vtuber\Miniconda3\Scripts\conda.exe"
$CondaModuleArgs = @{ChangePs1 = $True}
Import-Module "$Env:_CONDA_ROOT\shell\condabin\Conda.psm1" -ArgumentList $CondaModuleArgs

Remove-Variable CondaModuleArgs