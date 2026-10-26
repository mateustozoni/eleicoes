"""Dados totalmente sintéticos para testes; nenhuma assinatura oficial ou log bruto incluído."""
import functools,io,pathlib,zipfile
from datetime import datetime,timedelta
import asn1tools
ROOT=pathlib.Path(__file__).resolve().parents[1]
@functools.lru_cache(maxsize=1)
def synthetic_bu():
 codec=asn1tools.compile_files(str(ROOT/'docs/bu.asn1'),'ber')
 ident=dict(municipioZona=dict(municipio=1074,zona=4),local=1,secao=1)
 header=dict(dataGeracao='20261025T170100',idEleitoral=('idPleito',3221))
 votos=[]
 for index,(kind,code,n) in enumerate([('nominal',13,120),('nominal',22,75),('branco',None,3),('nulo',None,4)],1):
  vote=dict(tipoVoto=kind,quantidadeVotos=n,ordemGeracaoHash=index,hash=bytes(64))
  if code is not None:vote['identificacaoVotavel']=dict(partido=code,codigo=code)
  votos.append(vote)
 bu=dict(cabecalho=header,fase='oficial',urna=dict(tipoUrna='secao',versaoVotacao='SYNTHETIC TEST ONLY',tipoArquivo='votacaoUE',numeroSerieFV=bytes(4),correspondenciaResultado=dict(identificacao=('identificacaoSecaoEleitoral',ident),carga=dict(numeroInternoUrna=1,numeroSerieFC=bytes(4),identificadorGeradorMidia=dict(nome='SYNTHETIC',serialCertificadoTPM='SYNTHETIC',serialInstalacao='SYNTHETIC'),dataHoraCarga='20261024T080000',codigoCarga='0'*24))),identificacaoSecao=ident,dataHoraEmissao='20261025T170100',dadosSecaoSA=('dadosSecao',dict(dataHoraAbertura='20261025T080000',dataHoraEncerramento='20261025T170000')),qtdEleitoresCompareceram=202,detalhamentoComparecimento=dict(qtdEleitoresCompareceramSemBiometria=0,qtdEleitoresHabilitadosPorBiometria=202,qtdEleitoresHabilitadosPorBiografia=0),resultadosVotacaoPorEleicao=[dict(idEleicao=6258,qtdEleitoresAptos=262,qtdEleitoresAptosSecao=262,qtdEleitoresAptosTTE=0,resultadosVotacao=[dict(tipoCargo='majoritario',qtdComparecimento=202,totaisVotosCargo=[dict(codigoCargo=('cargoConstitucional','presidente'),ordemImpressao=1,votosVotaveis=votos)])],ultimoHashVotosVotavel=bytes(64),assinaturaUltimoHashVotosVotavel=bytes(128))],historicoCodigosCarga=['0'*24])
 payload=codec.encode('EntidadeBoletimUrna',bu)
 return codec.encode('EntidadeEnvelopeGenerico',dict(cabecalho=header,fase='oficial',identificacao=('identificacaoSecaoEleitoral',ident),tipoEnvelope='envelopeBoletimUrna',conteudo=payload))
def synthetic_log():
 events=[('08:00:00','Município: 01074'),('08:00:00','Zona Eleitoral: 0004'),('08:00:00','Seção Eleitoral: 0001')]
 start=datetime(2026,10,25,8,1)
 for i in range(202):
  when=start+timedelta(seconds=i*40)
  for delta,message in [(0,'Identificador do eleitor digitado pelo mesário'),(1,'Tipo de habilitação do eleitor [biométrica]'),(10,'Eleitor foi habilitado'),(30,'Voto confirmado para [Presidente]'),(31,'O voto do eleitor foi computado')]:events.append(((when+timedelta(seconds=delta)).strftime('%H:%M:%S'),message))
 text='\n'.join(f'25/10/2026 {when}\tINFO\t00000001\tVOTA\t{message}\t{index:016X}' for index,(when,message) in enumerate(events))
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w',zipfile.ZIP_DEFLATED) as z:z.writestr('logd.dat',text.encode('latin1'))
 return b.getvalue()
