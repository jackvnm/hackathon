import logging

from sqlalchemy.exc import SQLAlchemyError

from app.assignments import assign_analysis
from app.models import Analysis, IssueResponse
from app.services.classification import Classifier
from app.storage import Store

logger = logging.getLogger(__name__)


def classify_saved_issue(
    store: Store, classifier: Classifier, saved: IssueResponse,
    *, photo: bytes, media_type: str, description: str,
) -> IssueResponse:
    # Called only after the original photo and report transaction committed.
    try:
        analysis = Analysis.model_validate(classifier.classify(
            photo=photo, media_type=media_type, description=description,
        ))
    except Exception as exc:
        # SDK errors may contain request data; record only the exception type.
        logger.warning("Saved issue %s analysis failed (%s)", saved.id, type(exc).__name__)
        analysis = None
    try:
        if analysis is not None:
            analysis, assignment = assign_analysis(analysis)
            return store.save_analysis(saved.id, analysis, assignment)
        return store.save_analysis(saved.id, None)
    except SQLAlchemyError as exc:
        logger.error("Saved issue %s analysis persistence failed (%s)", saved.id, type(exc).__name__)
        # The original submission is already saved: never say 'not saved'.
        return saved.model_copy(update={"analysis_error": "Report saved; analysis result could not be saved. Dispatcher review required"})
