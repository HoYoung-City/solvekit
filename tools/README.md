# 선택적 실행 도구

반복 작업이 생겨 의존관계, 결과 근거, 계층별 도식을 함께 관리하고 싶을 때 사용합니다.
도구를 쓰기 위한 파일 형식과 명령은 아래에 있습니다. 방법론만 참고할 때는 사용할 필요가 없습니다.

이 도구는 작업 상태와 문서를 관리합니다. 실제 분석·개발은 사람이나 AI가 수행하며, 모델 호출이나 외부 명령 실행 기능은 없습니다.

## 최소 사용법

저장소의 `tools/` 폴더에서 실행합니다. Python 3.10 이상, 추가 패키지 없음.

```bash
cd tools
python -m methodkit list
python -m methodkit start --pattern build --goal "입력 파일의 구조를 설명하는 작은 도구" --run runs/example
python -m methodkit next runs/example
```

`runs/example/run.json`에 작업과 상태, `report.md`에 L0~L2 Mermaid 도식과 L3 작업 설명이 생깁니다.
`--goal`에는 이번 실행에서 다룰 내용을 적습니다. 잠정적인 설명으로 시작해 나중에 바꿀 수 있습니다.
예시 패턴의 단계·의존관계가 현재 문제에 맞는지 보고 필요한 만큼 수정합니다.

실제 확인 내용을 `runs/example/evidence/problem.txt`에 작성했다면 완료를 기록할 수 있습니다.
아래 명령은 그 파일이 이미 존재할 때 실행하는 예입니다.

```bash
python -m methodkit complete runs/example frame --result "입력 범위와 확인할 내용을 정리했다" --evidence evidence/problem.txt
python -m methodkit next runs/example
```

도식은 `report.md`를 Mermaid 지원 뷰어로 열어 봅니다. 생성됐다는 사실이 사람의 이해나 결과의 정확성을 보장하지는 않습니다.

## 패턴 예시

네 예시는 도구의 구조를 보여 주는 수정 가능한 `seed`입니다. 문제를 먼저 네 가지 중 하나로 분류할 필요는 없습니다.

| 파일 | 다루는 질문 |
|---|---|
| [discover.json](patterns/discover.json) | 불명확한 상황에서 무엇을 더 알아야 하는가 |
| [investigate.json](patterns/investigate.json) | 관측한 현상을 무엇으로 설명할 수 있는가 |
| [build.json](patterns/build.json) | 필요한 결과를 실제로 어떻게 제공하는가 |
| [decide.json](patterns/decide.json) | 어떤 대안이 현재 조건에 맞는가 |

각 예시는 첫 결과, 부족점 확인, 세부 작업, 통합과 확인을 담고 있습니다. 단계 수와 순서는 바꿀 수 있습니다.
새 작업 구조를 쓰려면 예시 JSON을 복사해 수정한 뒤 `--pattern-file PATH`를 사용합니다.

| 주요 필드 | 의미 |
|---|---|
| `phases` | 상위 단계의 ID와 표시 이름 |
| `steps[].id`, `label`, `phase` | 작업 ID, 이름, 소속 단계 |
| `depends_on` | 먼저 완료되어야 할 작업 ID |
| `inputs`, `output`, `acceptance` | 입력, 결과물, 확인 기준 |
| `writes` | 함께 수정하면 충돌하는 파일·자원의 논리적 이름 |
| `applicable_when`, `avoid_when` | 패턴의 적용 조건과 주의할 조건 |

작업 ID는 영문 소문자로 시작하며 영문 소문자·숫자·하이픈을 사용합니다. 실행 의존관계는 순환 없이 정의합니다.
반복 개선은 완료한 작업을 다시 열거나 작업 구조를 수정해서 표현합니다.

## 명령어

아래 명령 앞에는 모두 `python -m methodkit`을 붙입니다. `DIR`은 실행 폴더입니다.

| 명령 | 용도 |
|---|---|
| `list` | 예시 패턴 목록 |
| `start --pattern TYPE --goal TEXT --run DIR` | 예시로 새 실행 시작 |
| `start --pattern-file FILE --goal TEXT --run DIR` | 수정한 패턴으로 시작 |
| `next DIR` | 가능한 작업과 충돌 없는 병렬 후보 |
| `complete DIR STEP --result TEXT --evidence FILE` | 결과와 근거 기록; 근거 여러 개는 옵션 반복 |
| `reopen DIR STEP --reason TEXT` | 해당 작업과 후속 결과를 다시 열기 |
| `revise DIR --reason TEXT` | 수정한 계획 반영; 기존 결과를 보관하고 현재 상태 초기화 |
| `render DIR` | 보고서 다시 생성 |
| `check DIR` | 구조와 기록한 근거 파일의 변경 여부 확인 |
| `retain DIR --outcome success --lesson TEXT --out FILE` | 경험을 재사용 후보로 보존; `partial`, `failure`도 가능 |

## 결과를 바꾸거나 다시 사용할 때

- 근거 파일은 실행 폴더 안에 있는 비어 있지 않은 파일을 사용합니다. 경로는 실행 폴더 기준입니다.
- `complete`는 파일의 존재와 해시를 기록합니다. 내용의 진실성이나 완료 기준 충족 여부는 별도로 판단합니다.
- 결과나 근거가 바뀌면 `reopen`으로 관련 작업과 후속 작업을 다시 엽니다. `run.json`의 문제·계획을 수정했다면 `revise`를 사용합니다.
- `next`의 병렬 후보는 `depends_on`과 `writes`에 따른 제안입니다. 같은 자원은 같은 이름으로 적고, `run.json`에 쓰는 명령은 한 실행 주체가 직렬로 수행합니다.
- `retain`의 `success`는 모든 작업 완료를 요구합니다. 보존 결과는 `candidate`이며 자동 채택·공개하지 않습니다.
- 실제 입력과 비공개 사례는 `runs/`, `cases-private/`에 둡니다. 두 경로는 Git 추적에서 제외되지만 다른 위치에 복사한 파일까지 보호하지는 않습니다.

## 도구 검증

`tools/` 폴더에서 실행합니다.

```bash
python -m unittest discover -s tests -v
```

의존관계, 근거 변경 감지, 후속 결과 무효화, 사례 기록을 검사합니다. 방법론의 효과나 생성된 도식의 가독성을 자동 평가하는 검사는 아닙니다.
