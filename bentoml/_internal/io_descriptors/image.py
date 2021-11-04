import io
import typing as t

from starlette.requests import Request
from starlette.responses import StreamingResponse

import bentoml._internal.constants as const

from ...exceptions import BentoMLException, InvalidArgument
from ..utils import LazyLoader
from .base import IODescriptor

if t.TYPE_CHECKING:  # pragma: no cover
    # pylint: disable=unused-import
    import numpy as np
    import PIL
    import PIL.Image
else:
    np = LazyLoader("np", globals(), "numpy")

    # NOTE: pillow-simd only benefits users who want to do preprocessing
    # TODO: add options for users to choose between simd and native mode
    _exc = const.IMPORT_ERROR_MSG.format(
        fwr="Pillow",
        module=f"{__name__}.Image",
        inst="`pip install Pillow`",
    )
    PIL = LazyLoader("PIL", globals(), "PIL", exc_msg=_exc)
    PIL.Image = LazyLoader("PIL.Image", globals(), "PIL.Image", exc_msg=_exc)

DEFAULT_PIL_MODE = "RGB"


class Image(IODescriptor):
    """
    `Image` defines API specification for the inputs/outputs of a Service, where either inputs will be
    converted to or outputs will be converted from images as specified in your API function signature.

    .. Toy implementation of a transformers service for object detection::
        #obj_detc.py
        import bentoml
        from bentoml.io import Image, JSON
        import bentoml.transformers

        tag='google_vit_large_patch16_224:latest'
        runner = bentoml.transformers.load_runner(tag, tasks='image-classification',device=-1,feature_extractor="google/vit-large-patch16-224")

        svc = bentoml.Service("vit-object-detection", runners=[runner])

        @svc.api(input=Image(), output=JSON())
        def predict(input_img):
            res = runner.run_batch(input_img)
            return res

    Users then can then serve this service with `bentoml serve`::
        % bentoml serve ./obj_detc.py:svc --auto-reload

        (Press CTRL+C to quit)
        [INFO] Starting BentoML API server in development mode with auto-reload enabled
        [INFO] Serving BentoML Service "vit-object-detection" defined in "obj_detc.py"
        [INFO] API Server running on http://0.0.0.0:5000

    Users can then send a cURL requests like shown in different terminal session::
        # we will run on our input image test.png
        # image can get from http://images.cocodataset.org/val2017/000000039769.jpg
        % curl -H "Content-Type: multipart/form-data" -F 'fileobj=@test.jpg;type=image/jpeg' http://0.0.0.0:8000/predict

        [{"score":0.8610631227493286,"label":"Egyptian cat"},{"score":0.08770329505205154,"label":"tabby, tabby cat"},{"score":0.03540956228971481,"label":"tiger cat"},{"score":0.004140055272728205,"label":"lynx, catamount"},{"score":0.0009498853469267488,"label":"Siamese cat, Siamese"}]%

    Args:
        pilmode (`str`, `optional`, default to `RGB`):
            Color mode for PIL.
        mime_type (`str`, `optional`, default to `image/jpeg`):
            Return MIME type for `starlette.response.StreamingResponse`

    Returns:
        IO Descriptor that represents either a `np.ndarray` or a `PIL.Image.Image`.
    """

    def __init__(self, pilmode=DEFAULT_PIL_MODE, mime_type: str = "image/jpeg"):
        self._pilmode = pilmode
        self._mime_type = mime_type
        self._ext = mime_type.split("/")[-1].upper()

    def openapi_request_schema(self) -> t.Dict[str, t.Any]:
        """Returns OpenAPI schema for incoming requests"""

    def openapi_responses_schema(self) -> t.Dict[str, t.Any]:
        """Returns OpenAPI schema for outcoming responses"""

    async def from_http_request(self, request: Request) -> "PIL.Image":
        content_type = request.headers["content-type"].split(";")[0]
        if content_type != "multipart/form-data":
            raise BentoMLException(
                f"{self.__class__.__name__} should have `Content-Type: multipart/form-data`, got {content_type} instead"
            )
        form = await request.form()
        contents = await form[list(form.keys()).pop()].read()
        return PIL.Image.open(io.BytesIO(contents))

    async def to_http_response(
        self, obj: t.Union["np.ndarray", "PIL.Image.Image"]
    ) -> StreamingResponse:
        if not any(isinstance(obj, i) for i in [np.ndarray, PIL.Image.Image]):
            raise InvalidArgument(
                f"Unsupported Image type received: {type(obj)},"
                f" `{self.__class__.__name__}` supports only `np.ndarray` and `PIL.Image`"
            )
        image = PIL.Image.fromarray(obj) if isinstance(obj, np.ndarray) else obj

        # TODO: Support other return types?
        ret = io.BytesIO()
        image.save(ret, self._ext)
        return StreamingResponse(ret, media_type=self._mime_type)