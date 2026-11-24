param([string]$TextFile,[string]$OutputFile,[string]$VoiceName='',[int]$Rate=0,[int]$Volume=90)
Add-Type -AssemblyName System.Speech
$s=New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
 if($VoiceName){
  try{$s.SelectVoice($VoiceName)}catch{}
 }else{
  $preferred=$s.GetInstalledVoices() | Where-Object { $_.Enabled -and $_.VoiceInfo.Culture.Name -like 'es-*' } | Select-Object -First 1
  if($preferred){$s.SelectVoice($preferred.VoiceInfo.Name)}else{try{$s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet,[System.Speech.Synthesis.VoiceAge]::NotSet,0,[System.Globalization.CultureInfo]::GetCultureInfo('es-MX'))}catch{}}
 }
 $s.Rate=[Math]::Max(-10,[Math]::Min(10,$Rate));$s.Volume=[Math]::Max(0,[Math]::Min(100,$Volume))
 $format=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(24000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
 $s.SetOutputToWaveFile($OutputFile,$format)
 $raw=[System.IO.File]::ReadAllText($TextFile,[System.Text.Encoding]::UTF8)
 $escaped=[System.Security.SecurityElement]::Escape($raw)
 $escaped=$escaped -replace '([.!?])\s+','$1<break time="200ms"/> '
 $escaped=$escaped -replace ',\s+',',<break time="90ms"/> '
 $ssml="<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='es-MX'><prosody rate='0%'>$escaped</prosody></speak>"
 try{$s.SpeakSsml($ssml)}catch{$s.Speak($raw)}
}finally{$s.Dispose()}
