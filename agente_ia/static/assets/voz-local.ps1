param([string]$TextFile,[string]$OutputFile,[string]$VoiceName='',[int]$Rate=0,[int]$Volume=90)
Add-Type -AssemblyName System.Speech
$s=New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
 if($VoiceName){$s.SelectVoice($VoiceName)}else{try{$s.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet,[System.Speech.Synthesis.VoiceAge]::NotSet,0,[System.Globalization.CultureInfo]::GetCultureInfo('es-MX'))}catch{}}
 $s.Rate=$Rate;$s.Volume=$Volume
 $format=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
 $s.SetOutputToWaveFile($OutputFile,$format)
 $s.Speak([System.IO.File]::ReadAllText($TextFile,[System.Text.Encoding]::UTF8))
}finally{$s.Dispose()}
