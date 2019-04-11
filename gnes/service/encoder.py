import zmq

from .base import BaseService as BS, ComponentNotLoad, ServiceMode, ServiceError, MessageHandler
from ..document import MultiSentDocument, DocumentMapper
from ..encoder import PipelineEncoder
from ..messaging import *


class EncoderService(BS):
    handler = MessageHandler(BS.handler)

    def _post_init(self):
        self._model = None
        try:
            self._model = PipelineEncoder.load(self.args.dump_path)
            self.logger.info('load a trained encoder')
        except FileNotFoundError:
            if self.args.mode == ServiceMode.TRAIN:
                try:
                    self._model = PipelineEncoder.load_yaml(self.args.yaml_path)
                    self.logger.info('load an uninitialized encoder, training is needed!')
                except FileNotFoundError:
                    raise ComponentNotLoad
            else:
                raise ComponentNotLoad

    def _raise_empty_model_error(self):
        raise ValueError('no model config available, exit!')

    @handler.register(Message.typ_default)
    def _handler_default(self, msg: 'Message', out: 'zmq.Socket'):
        doc_mapper = DocumentMapper(MultiSentDocument.from_list(msg.msg_content))
        sent_ids, sents = doc_mapper.sent_id_sentence
        if not sents:
            raise ServiceError('received an empty list, nothing to do')
        if self.args.mode == ServiceMode.TRAIN:
            self._model.train(sents)
            self.is_model_changed.set()
        elif self.args.mode == ServiceMode.ADD:
            vecs = self._model.encode(sents)
            send_message(out, msg.copy_mod(msg_content=(sent_ids, vecs)), self.args.timeout)
            send_message(out, msg.copy_mod(msg_content=doc_mapper.sent_id_doc_id, msg_type=Message.typ_sent_id),
                         self.args.timeout)
            send_message(out, msg.copy_mod(msg_content=doc_mapper.doc_id_document, msg_type=Message.typ_doc_id),
                         self.args.timeout)
        elif self.args.mode == ServiceMode.QUERY:
            vecs = self._model.encode(sents)
            send_message(out, msg.copy_mod(msg_content=vecs), self.args.timeout)
        else:
            raise ServiceError('service %s runs in unknown mode %s' % (self.__class__.__name__, self.args.mode))