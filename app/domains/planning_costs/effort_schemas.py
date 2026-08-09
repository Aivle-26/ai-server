"""KOSA 직무 기반 WBS 공수 산정 API 스키마."""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.api_types import LLMStatus, ProjectId, WbsId


class KosaJobCategory(str, Enum):
    아이티_기획자 = "IT 기획자"
    아이티_컨설턴트 = "IT 컨설턴트"
    업무분석가 = "업무분석가"
    데이터분석가 = "데이터분석가"
    아이티_피엠 = "IT PM"
    아이티_아키텍트 = "IT 아키텍트"
    사용자환경_기획개발자 = "UI/UX 기획·개발자"
    사용자환경_디자이너 = "UI/UX 디자이너"
    응용_소프트웨어_개발자 = "응용 SW 개발자"
    시스템_소프트웨어_개발자 = "시스템 SW 개발자"
    정보시스템운용자 = "정보시스템운용자"
    아이티_지원기술자 = "IT 지원기술자"
    아이티_마케터 = "IT 마케터"
    아이티_품질관리자 = "IT 품질관리자"
    아이티_테스터 = "IT 테스터"
    아이티_감리 = "IT 감리"
    정보보안전문가 = "정보보안전문가"


class KosaDetailedJob(str, Enum):
    일반_아이티_기획자 = "IT 기획자"
    빅데이터기획자 = "빅데이터기획자"
    인공지능서비스_기획자 = "인공지능서비스 기획자"
    일반_아이티_컨설턴트 = "IT 컨설턴트"
    정보보호컨설턴트 = "정보보호컨설턴트"
    업무분석가 = "업무분석가"
    데이터분석가 = "데이터분석가"
    아이티_피엠 = "IT PM"
    일반_아이티_아키텍트 = "IT 아키텍트"
    소프트웨어_아키텍트 = "SW 아키텍트"
    인프라스트럭처_아키텍트 = "인프라스트럭처 아키텍트"
    데이터_아키텍트 = "데이터 아키텍트"
    데이터베이스_아키텍트 = "데이터베이스 아키텍트"
    빅데이터_아키텍트 = "빅데이터 아키텍트"
    인공지능_아키텍트 = "인공지능 아키텍트"
    일반_사용자환경_기획개발자 = "UI/UX 기획·개발자"
    사용자환경_기획자 = "UI/UX 기획자"
    사용자환경_개발자 = "UI/UX 개발자"
    사용자환경_디자이너 = "UI/UX 디자이너"
    일반_응용_소프트웨어_개발자 = "응용 SW 개발자"
    빅데이터_개발자 = "빅데이터 개발자"
    인공지능_소프트웨어_개발자 = "인공지능 SW 개발자"
    일반_시스템_소프트웨어_개발자 = "시스템 SW 개발자"
    임베디드_소프트웨어_개발자 = "임베디드 SW 개발자"
    일반_정보시스템운용자 = "정보시스템운용자"
    데이터베이스운용자 = "데이터베이스운용자"
    네트워크_엔지니어 = "NW 엔지니어"
    아이티_시스템운용자 = "IT 시스템운용자"
    빅데이터엔지니어 = "빅데이터엔지니어"
    인공지능_서비스운용자 = "인공지능 서비스운용자"
    아이티_지원기술자 = "IT 지원기술자"
    일반_아이티_마케터 = "IT 마케터"
    소프트웨어_제품기획자 = "SW 제품기획자"
    아이티_서비스기획자 = "IT 서비스기획자"
    아이티_기술영업 = "IT 기술영업"
    아이티_품질관리자 = "IT 품질관리자"
    아이티_테스터 = "IT 테스터"
    아이티_감리 = "IT 감리"
    일반_정보보안전문가 = "정보보안전문가"
    정보보호관리자 = "정보보호관리자"
    침해사고대응전문가 = "침해사고대응전문가"


DETAILED_JOB_CATEGORY: dict[KosaDetailedJob, KosaJobCategory] = {
    KosaDetailedJob.일반_아이티_기획자: KosaJobCategory.아이티_기획자,
    KosaDetailedJob.빅데이터기획자: KosaJobCategory.아이티_기획자,
    KosaDetailedJob.인공지능서비스_기획자: KosaJobCategory.아이티_기획자,
    KosaDetailedJob.일반_아이티_컨설턴트: KosaJobCategory.아이티_컨설턴트,
    KosaDetailedJob.정보보호컨설턴트: KosaJobCategory.아이티_컨설턴트,
    KosaDetailedJob.업무분석가: KosaJobCategory.업무분석가,
    KosaDetailedJob.데이터분석가: KosaJobCategory.데이터분석가,
    KosaDetailedJob.아이티_피엠: KosaJobCategory.아이티_피엠,
    KosaDetailedJob.일반_아이티_아키텍트: KosaJobCategory.아이티_아키텍트,
    KosaDetailedJob.소프트웨어_아키텍트: KosaJobCategory.아이티_아키텍트,
    KosaDetailedJob.인프라스트럭처_아키텍트: KosaJobCategory.아이티_아키텍트,
    KosaDetailedJob.데이터_아키텍트: KosaJobCategory.아이티_아키텍트,
    KosaDetailedJob.데이터베이스_아키텍트: KosaJobCategory.아이티_아키텍트,
    KosaDetailedJob.빅데이터_아키텍트: KosaJobCategory.아이티_아키텍트,
    KosaDetailedJob.인공지능_아키텍트: KosaJobCategory.아이티_아키텍트,
    KosaDetailedJob.일반_사용자환경_기획개발자: KosaJobCategory.사용자환경_기획개발자,
    KosaDetailedJob.사용자환경_기획자: KosaJobCategory.사용자환경_기획개발자,
    KosaDetailedJob.사용자환경_개발자: KosaJobCategory.사용자환경_기획개발자,
    KosaDetailedJob.사용자환경_디자이너: KosaJobCategory.사용자환경_디자이너,
    KosaDetailedJob.일반_응용_소프트웨어_개발자: KosaJobCategory.응용_소프트웨어_개발자,
    KosaDetailedJob.빅데이터_개발자: KosaJobCategory.응용_소프트웨어_개발자,
    KosaDetailedJob.인공지능_소프트웨어_개발자: KosaJobCategory.응용_소프트웨어_개발자,
    KosaDetailedJob.일반_시스템_소프트웨어_개발자: KosaJobCategory.시스템_소프트웨어_개발자,
    KosaDetailedJob.임베디드_소프트웨어_개발자: KosaJobCategory.시스템_소프트웨어_개발자,
    KosaDetailedJob.일반_정보시스템운용자: KosaJobCategory.정보시스템운용자,
    KosaDetailedJob.데이터베이스운용자: KosaJobCategory.정보시스템운용자,
    KosaDetailedJob.네트워크_엔지니어: KosaJobCategory.정보시스템운용자,
    KosaDetailedJob.아이티_시스템운용자: KosaJobCategory.정보시스템운용자,
    KosaDetailedJob.빅데이터엔지니어: KosaJobCategory.정보시스템운용자,
    KosaDetailedJob.인공지능_서비스운용자: KosaJobCategory.정보시스템운용자,
    KosaDetailedJob.아이티_지원기술자: KosaJobCategory.아이티_지원기술자,
    KosaDetailedJob.일반_아이티_마케터: KosaJobCategory.아이티_마케터,
    KosaDetailedJob.소프트웨어_제품기획자: KosaJobCategory.아이티_마케터,
    KosaDetailedJob.아이티_서비스기획자: KosaJobCategory.아이티_마케터,
    KosaDetailedJob.아이티_기술영업: KosaJobCategory.아이티_마케터,
    KosaDetailedJob.아이티_품질관리자: KosaJobCategory.아이티_품질관리자,
    KosaDetailedJob.아이티_테스터: KosaJobCategory.아이티_테스터,
    KosaDetailedJob.아이티_감리: KosaJobCategory.아이티_감리,
    KosaDetailedJob.일반_정보보안전문가: KosaJobCategory.정보보안전문가,
    KosaDetailedJob.정보보호관리자: KosaJobCategory.정보보안전문가,
    KosaDetailedJob.침해사고대응전문가: KosaJobCategory.정보보안전문가,
}


class EffortWBSTask(BaseModel):
    model_config = ConfigDict(extra="ignore")

    wbs_id: WbsId
    wbs_name: str = Field(max_length=200)
    description: str = Field(max_length=4_000)
    start_date: date | None = None
    end_date: date | None = None

    @model_validator(mode="after")
    def validate_task(self) -> "EffortWBSTask":
        self.wbs_name = self.wbs_name.strip()
        self.description = self.description.strip()
        if not self.wbs_name or not self.description:
            raise ValueError("WBS 작업명과 설명은 비어 있을 수 없습니다.")
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("WBS 종료일은 시작일보다 빠를 수 없습니다.")
        return self


class PlanningEffortEstimateRequest(BaseModel):
    project_id: ProjectId
    project_name: str = Field(max_length=200)
    wbs_tasks: list[EffortWBSTask] = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def validate_request(self) -> "PlanningEffortEstimateRequest":
        self.project_name = self.project_name.strip()
        if not self.project_name:
            raise ValueError("프로젝트명은 비어 있을 수 없습니다.")
        wbs_ids = [task.wbs_id for task in self.wbs_tasks]
        if len(wbs_ids) != len(set(wbs_ids)):
            raise ValueError("WBS ID는 중복될 수 없습니다.")
        return self


class WBSEffortEstimate(BaseModel):
    wbs_id: WbsId
    wbs_name: str
    kosa_job_category: KosaJobCategory
    detailed_job: KosaDetailedJob
    estimated_person_days: float = Field(gt=0)
    estimated_mm: float = Field(gt=0)
    estimation_reason: str
    confidence: float = Field(ge=0, le=1)


class KosaJobEffort(BaseModel):
    kosa_job_category: KosaJobCategory
    detailed_job: KosaDetailedJob
    estimated_person_days: float = Field(gt=0)
    estimated_mm: float = Field(gt=0)
    wbs_ids: list[WbsId] = Field(min_length=1)


class PlanningEffortEstimateResponse(BaseModel):
    project_id: ProjectId
    workdays_per_month: float = Field(gt=0)
    wbs_efforts: list[WBSEffortEstimate] = Field(min_length=1)
    job_efforts: list[KosaJobEffort] = Field(min_length=1)
    total_estimated_person_days: float = Field(gt=0)
    total_estimated_mm: float = Field(gt=0)
    llm_status: LLMStatus
