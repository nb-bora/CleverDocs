$ErrorActionPreference = "Stop"

Set-Location "F:\CleverDocs"

$expected = @(
  "app\domain\common\entity.py",
  "app\domain\common\value_object.py",
  "app\domain\common\events.py",
  "app\domain\common\exceptions.py",

  "app\domain\organization\entities\organization.py",
  "app\domain\organization\entities\membership.py",
  "app\domain\organization\repositories\organization_repository.py",

  "app\domain\identity\entities\user.py",
  "app\domain\identity\entities\role.py",
  "app\domain\identity\entities\permission.py",
  "app\domain\identity\services\authorization_policy.py",
  "app\domain\identity\services\document_policy.py",
  "app\domain\identity\repositories\user_repository.py",

  "app\domain\document\aggregates\document.py",
  "app\domain\document\aggregates\document_versioning.py",
  "app\domain\document\value_objects\document_status.py",
  "app\domain\document\value_objects\file_type.py",
  "app\domain\document\events\document_uploaded.py",
  "app\domain\document\events\document_processed.py",
  "app\domain\document\events\document_indexed.py",
  "app\domain\document\events\document_failed.py",
  "app\domain\document\events\document_version_added.py",
  "app\domain\document\events\document_reindex_requested.py",
  "app\domain\document\repositories\document_repository.py",

  "app\domain\processing\entities\document_content.py",
  "app\domain\processing\services\ocr_service.py",
  "app\domain\processing\services\text_cleaner.py",

  "app\domain\search\value_objects\search_query.py",
  "app\domain\search\services\search_engine.py",
  "app\domain\search\read_models\search_result.py",

  "app\application\common\unit_of_work.py",
  "app\application\common\event_publisher.py",
  "app\application\commands\upload_document.py",
  "app\application\commands\archive_document.py",
  "app\application\commands\add_document_version.py",
  "app\application\commands\request_reindex.py",
  "app\application\handlers\upload_document_handler.py",
  "app\application\handlers\archive_document_handler.py",
  "app\application\handlers\add_document_version_handler.py",
  "app\application\handlers\request_reindex_handler.py",
  "app\application\queries\search_documents.py",
  "app\application\queries\get_document.py",
  "app\application\queries\get_document_status_timeline.py",
  "app\application\auth\require_permission.py",

  "app\infrastructure\db\orm\base.py",
  "app\infrastructure\db\orm\models\organization_model.py",
  "app\infrastructure\db\orm\models\membership_model.py",
  "app\infrastructure\db\orm\models\user_model.py",
  "app\infrastructure\db\orm\models\role_model.py",
  "app\infrastructure\db\orm\models\permission_model.py",
  "app\infrastructure\db\orm\models\document_model.py",
  "app\infrastructure\db\orm\models\document_content_model.py",
  "app\infrastructure\db\orm\models\audit_log_model.py",
  "app\infrastructure\db\repositories\organization_repository_sql.py",
  "app\infrastructure\db\repositories\user_repository_sql.py",
  "app\infrastructure\db\repositories\document_repository_sql.py",
  "app\infrastructure\db\session.py",
  "app\infrastructure\db\unit_of_work_sql.py",

  "app\infrastructure\audit\audit_logger.py",
  "app\infrastructure\storage\local_file_storage.py",
  "app\infrastructure\storage\s3_file_storage.py",
  "app\infrastructure\messaging\event_bus.py",
  "app\infrastructure\messaging\outbox\outbox_model.py",
  "app\infrastructure\messaging\outbox\outbox_publisher.py",
  "app\infrastructure\messaging\outbox\outbox_dispatcher.py",
  "app\infrastructure\ocr\easyocr_adapter.py",
  "app\infrastructure\ocr\tesseract_adapter.py",
  "app\infrastructure\ocr\ocr_service_impl.py",
  "app\infrastructure\search\opensearch_client.py",
  "app\infrastructure\search\search_engine_impl.py",

  "app\interfaces\api\main.py",
  "app\interfaces\api\deps.py",
  "app\interfaces\api\middleware\auth_middleware.py",
  "app\interfaces\api\middleware\tenant_context.py",
  "app\interfaces\api\routes\auth.py",
  "app\interfaces\api\routes\organizations.py",
  "app\interfaces\api\routes\documents.py",
  "app\interfaces\api\routes\search.py",
  "app\interfaces\api\schemas\auth.py",
  "app\interfaces\api\schemas\organizations.py",
  "app\interfaces\api\schemas\documents.py",
  "app\interfaces\api\schemas\search.py",

  "app\projections\search_projection_consumer.py",
  "app\projections\search_reindex_consumer.py",
  "app\workers\ocr_worker.py",
  "app\workers\indexing_worker.py"
)

$missing = @()
foreach ($p in $expected) {
  if (-not (Test-Path -LiteralPath $p)) { $missing += $p }
}

if ($missing.Count -eq 0) {
  Write-Output "ALL_EXPECTED_PRESENT"
  exit 0
}

Write-Output "MISSING ($($missing.Count))"
$missing | ForEach-Object { Write-Output $_ }
exit 2

