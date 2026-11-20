// SPDX-License-Identifier: MIT
// Keep a reviewed command and all of its descendants inside a kill-on-close job.
#include <windows.h>
#include <string>
#include <iostream>

static std::wstring quote(const wchar_t* value) {
    std::wstring out=L"\""; unsigned slashes=0;
    for (const wchar_t* p=value; *p; ++p) {
        if (*p==L'\\') { ++slashes; continue; }
        if (*p==L'"') { out.append(slashes*2+1,L'\\'); out+=L'"'; }
        else { out.append(slashes,L'\\'); out+=*p; }
        slashes=0;
    }
    out.append(slashes*2,L'\\'); return out+L'"';
}
int wmain(int argc,wchar_t** argv) {
    if (argc<2) return 2;
    HANDLE job=CreateJobObjectW(nullptr,nullptr);
    if (!job) return 3;
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION limits{};
    limits.BasicLimitInformation.LimitFlags=JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
    if (!SetInformationJobObject(job,JobObjectExtendedLimitInformation,&limits,sizeof(limits))) {CloseHandle(job);return 4;}
    std::wstring command;
    for(int i=1;i<argc;++i) {if(i>1)command+=L' ';command+=quote(argv[i]);}
    STARTUPINFOW start{};start.cb=sizeof(start);start.dwFlags=STARTF_USESTDHANDLES;
    start.hStdInput=GetStdHandle(STD_INPUT_HANDLE);start.hStdOutput=GetStdHandle(STD_OUTPUT_HANDLE);start.hStdError=GetStdHandle(STD_ERROR_HANDLE);
    PROCESS_INFORMATION process{};
    if (!CreateProcessW(argv[1],command.data(),nullptr,nullptr,TRUE,CREATE_SUSPENDED|CREATE_NO_WINDOW,nullptr,nullptr,&start,&process)) {CloseHandle(job);return 5;}
    if (!AssignProcessToJobObject(job,process.hProcess)) {TerminateProcess(process.hProcess,6);CloseHandle(process.hThread);CloseHandle(process.hProcess);CloseHandle(job);return 6;}
    ResumeThread(process.hThread);CloseHandle(process.hThread);
    WaitForSingleObject(process.hProcess,INFINITE);DWORD code=1;GetExitCodeProcess(process.hProcess,&code);
    CloseHandle(process.hProcess);CloseHandle(job);return static_cast<int>(code);
}
