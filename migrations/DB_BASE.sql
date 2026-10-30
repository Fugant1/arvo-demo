-- Schema e Carga Inicial para Auditoria Médica TISS/TUSS (Arvo Demo)
PRAGMA foreign_keys = ON;

DROP TABLE IF EXISTS historico_procedimentos_paciente;
DROP TABLE IF EXISTS tabela_tuss_regras;
DROP TABLE IF EXISTS pacientes;

CREATE TABLE pacientes (
    cpf TEXT PRIMARY KEY,
    nome TEXT NOT NULL,
    carteirinha TEXT NOT NULL,
    plano TEXT NOT NULL,
    data_nascimento TEXT NOT NULL,
    sexo TEXT NOT NULL
);

CREATE TABLE tabela_tuss_regras (
    codigo_tuss TEXT PRIMARY KEY,
    tabela_tiss TEXT NOT NULL,
    descricao TEXT NOT NULL,
    categoria TEXT NOT NULL,
    valor_contratual REAL NOT NULL,
    janela_duplicidade_dias INTEGER DEFAULT 0,
    qtd_maxima_permitida INTEGER DEFAULT 99,
    requer_evidencia_laudo INTEGER DEFAULT 0,
    incluso_taxa_sala INTEGER DEFAULT 0,
    codigo_substituto_upcoding TEXT,
    valor_substituto REAL,
    clausula_contratual TEXT NOT NULL,
    diretriz_ans_tuss TEXT NOT NULL
);

CREATE TABLE historico_procedimentos_paciente (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cpf_paciente TEXT NOT NULL,
    codigo_tuss TEXT NOT NULL,
    descricao TEXT NOT NULL,
    data_execucao TEXT NOT NULL,
    guia_referencia TEXT NOT NULL,
    prestador TEXT NOT NULL,
    valor_pago REAL NOT NULL,
    status_pagamento TEXT NOT NULL,
    observacao TEXT,
    FOREIGN KEY (cpf_paciente) REFERENCES pacientes(cpf)
);

-- 1. Paciente do PDF (Carlos Eduardo Mendes da Silva)
INSERT INTO pacientes (cpf, nome, carteirinha, plano, data_nascimento, sexo) VALUES (
    '123.456.789-00',
    'CARLOS EDUARDO MENDES DA SILVA',
    '0034.8891.220194.00-1',
    'Executivo',
    '1978-05-14',
    'M'
);

-- 2. Histórico do paciente (incluindo TUSS 10101012 nos últimos 15 dias antes de 18/10/2026 e TC externa em 16/10/2026)
INSERT INTO historico_procedimentos_paciente (
    cpf_paciente, codigo_tuss, descricao, data_execucao, guia_referencia, prestador, valor_pago, status_pagamento, observacao
) VALUES
(
    '123.456.789-00',
    '10101012',
    'Consulta em consultório (no horário normal ou preestabelecido)',
    '2026-10-08',
    '2026.10.771002-1',
    'Hospital Santa Helena de São Paulo S.A. - Ambulatório Cirúrgico',
    250.00,
    'PAGO',
    'Consulta pré-operatória realizada há 10 dias (dentro da janela de retorno de 15 dias).'
),
(
    '123.456.789-00',
    '41001095',
    'Tomografia computadorizada de abdome total (abdome superior e pelve)',
    '2026-10-16',
    '2026.10.819200-9',
    'Pronto-Socorro Diagnóstico São Lucas S.A.',
    1120.00,
    'PAGO',
    'Exame realizado em pronto-socorro externo 2 dias antes da internação e apresentado impresso na admissão.'
),
(
    '123.456.789-00',
    '40304361',
    'Hemograma com contagem de plaquetas ou frações',
    '2026-08-10',
    '2026.08.501120-0',
    'Laboratório Central SP',
    45.00,
    'PAGO',
    'Exame ambulatorial de rotina realizado há mais de 60 dias.'
);

-- 3. Tabela de Preços Contratuais e Regras Clínicas TUSS/ANS para todos os códigos da Guia TISS
INSERT INTO tabela_tuss_regras (
    codigo_tuss, tabela_tiss, descricao, categoria, valor_contratual,
    janela_duplicidade_dias, qtd_maxima_permitida, requer_evidencia_laudo,
    incluso_taxa_sala, codigo_substituto_upcoding, valor_substituto,
    clausula_contratual, diretriz_ans_tuss
) VALUES
(
    '10101012', '22',
    'Consulta em consultório (no horário normal ou preestabelecido) - Pré-operatória',
    'HONORARIOS_MEDICOS', 250.00,
    15, 1, 0, 0, NULL, NULL,
    'Cláusula 4.2 do Contrato Operadora-Prestador c/c Resolução Normativa ANS nº 465/2021 (Art. 12)',
    'É vedada a cobrança de nova consulta eletiva (TUSS 10101012) em intervalo inferior a 15 dias para o mesmo paciente (retorno/duplicidade) ou na data de admissão hospitalar de urgência/internação cirúrgica.'
),
(
    '31005128', '22',
    'Colecistectomia com colangiografia por videolaparoscopia (Via principal)',
    'PROCEDIMENTO_CIRURGICO', 4850.00,
    30, 1, 1, 0, '31005136', 3650.00,
    'Cláusula 7.1 do Contrato Operadora-Prestador c/c Diretriz de Utilização ANS (DUT nº 112 / Tabela TUSS 22)',
    'A cobrança do código TUSS 31005128 exige comprovação documental da realização da colangiografia transoperatória na descrição cirúrgica. Quando o relatório operatório atesta que NÃO foi realizada colangiografia, configura-se upcoding, cabendo glosa técnica ou reclassificação para TUSS 31005136 (Colecistectomia sem colangiografia por videolaparoscopia - R$ 3.650,00, diferença indevida de R$ 1.200,00 ou glosa do código cobrado indevidamente).'
),
(
    '31009050', '22',
    'Laparotomia exploradora, ou para biópsia, ou para drenagem de abscesso',
    'PROCEDIMENTO_CIRURGICO', 2300.00,
    30, 1, 1, 0, NULL, NULL,
    'Cláusula 7.4 do Contrato Operadora-Prestador c/c Normas Gerais de Auditoria TUSS/CBHPM (Item 4.3 - Vias de Acesso)',
    'Procedimento de cirurgia aberta (Laparotomia exploradora - TUSS 31009050) é excludente e incompatível com cirurgia realizada por acesso exclusivamente videolaparoscópico sem conversão para cirurgia aberta (unbundling cirúrgico). Glosa integral obrigatória de R$ 2.300,00.'
),
(
    '40304361', '22',
    'Hemograma com contagem de plaquetas ou frações (eritrograma, leucograma, plaquetas)',
    'SADT_EXAMES', 45.00,
    0, 4, 0, 0, NULL, NULL,
    'Cláusula 5.1 do Contrato Operadora-Prestador (Exames Laboratoriais de Rotina)',
    'Item de baixo valor unitário (R$ 45,00) permitido para controle pré e pós-operatório em internação cirúrgica até 4 execuções.'
),
(
    '41001095', '22',
    'Tomografia computadorizada de abdome total (abdome superior e pelve)',
    'SADT_EXAMES', 1120.00,
    15, 1, 1, 0, NULL, NULL,
    'Cláusula 5.8 do Contrato Operadora-Prestador c/c Padrão TISS ANS (Auditoria de SADT em Internação)',
    'Vedado o faturamento de exame de imagem de alto custo (TUSS 41001095) quando já realizado em serviço externo nos últimos 15 dias e trazido pelo próprio paciente na admissão, sem execução ou laudo emitido durante a internação.'
),
(
    '10102019', '22',
    'Visita hospitalar (pac. internado) - Evolução clínica enfermaria/apartamento',
    'HONORARIOS_MEDICOS', 190.00,
    0, 1, 0, 0, NULL, NULL,
    'Cláusula 4.5 do Contrato Operadora-Prestador c/c Normas Gerais CBHPM/TUSS (Item 2.1)',
    'Permitida no máximo 1 visita hospitalar por dia de internação pós-operatória (limite QTD=1 para o dia 19/10/2026).'
),
(
    '60000511', '18',
    'Diária de Apartamento Standard (com banheiro privativo e direito a acompanhante)',
    'DIARIAS', 980.00,
    0, 2, 0, 0, NULL, NULL,
    'Cláusula 3.1 do Contrato Operadora-Prestador (Tabela TUSS 18 - Diárias Hospitalares)',
    'Diária de Apartamento Standard remunerada conforme tempo de internação efetivo (admissão 18/10/2026 e alta 20/10/2026 = 2 diárias autorizadas).'
),
(
    '60001020', '18',
    'Diária de Unidade de Terapia Intensiva (UTI Adulto Geral - Tipo III)',
    'DIARIAS', 2650.00,
    0, 10, 1, 0, NULL, NULL,
    'Cláusula 3.4 do Contrato Operadora-Prestador c/c Padrão TISS ANS (Tabela 18 - Diárias de UTI)',
    'A cobrança de Diária de UTI (TUSS 60001020) exige comprovação de admissão e permanência em leito intensivo no relatório clínico. Caso o paciente tenha permanecido exclusivamente em Apartamento Standard sem passagem por UTI, aplica-se glosa integral de R$ 2.650,00.'
),
(
    '60023104', '18',
    'Taxa de Sala Cirúrgica Porte 4 (Inclui recuperação pós-anestésica imediata - RPA)',
    'TAXAS', 1850.00,
    0, 1, 0, 0, NULL, NULL,
    'Cláusula 3.8 do Contrato Operadora-Prestador (Tabela TUSS 18 - Taxas de Sala Cirúrgica)',
    'Taxa de sala cirúrgica porte 4 compatível com colecistectomia videolaparoscópica; engloba o uso de Recuperação Pós-Anestésica (RPA) e insumos descartáveis básicos de sala (luvas, gazes, compressas).'
),
(
    '70409112', '19',
    'Trocarte descartável c/ lâmina protegida 10mm (Kit Videolaparoscopia)',
    'OPME', 420.00,
    0, 4, 1, 0, NULL, NULL,
    'Cláusula 8.2 do Contrato Operadora-Prestador (Tabela TUSS 19 - Materiais Especiais / OPME)',
    'Autorizado o faturamento de até 3 a 4 trocartes descartáveis quando comprovado o acesso videolaparoscópico na descrição cirúrgica.'
),
(
    '70881204', '19',
    'Grampeador Linear Cortante Endoscópico Articulado 60mm + Carga Azul',
    'OPME', 3850.00,
    30, 1, 1, 0, NULL, NULL,
    'Cláusula 8.5 do Contrato Operadora-Prestador c/c Resolução Normativa ANS nº 424/2017 (Auditoria de OPME)',
    'Material especial de alto custo (TUSS 70881204) exige comprovação expressa de utilização na descrição técnica operatória. Na colecistectomia em que a ligadura da artéria e ducto cístico foi realizada exclusivamente com clipes metálicos LT-300, a cobrança de 3 grampeadores endoscópicos (R$ 11.550,00) constitui cobrança indevida integral.'
),
(
    '70201944', '19',
    'Clipe de Titânio p/ Ligadura Vascular LT-300 Médio/Grande (Cartucho c/ 6 un)',
    'OPME', 290.00,
    0, 3, 1, 0, NULL, NULL,
    'Cláusula 8.3 do Contrato Operadora-Prestador (Tabela TUSS 19 - OPME Videolaparoscopia)',
    'Compatível com ligadura de artéria e ducto cístico conforme descrito no ato operatório (2 cartuchos utilizados).'
),
(
    '70100210', '19',
    'Luva Cirúrgica Estéril Látex N. 7.5 + Compressas Gaze 7,5x7,5cm (Insumo Sala)',
    'OPME', 0.00,
    0, 0, 0, 1, NULL, NULL,
    'Cláusula 3.8.2 do Contrato Operadora-Prestador c/c Manual TISS ANS (Insumos Inclusos em Taxa de Sala)',
    'Luvas cirúrgicas estéreis e compressas de gaze (TUSS 70100210) são insumos operacionais básicos já remunerados integralmente na Taxa de Sala Cirúrgica (TUSS 60023104), sendo vedada sua cobrança avulsa como OPME (glosa integral de R$ 420,00).'
),
(
    '90114022', '20',
    'Ceftriaxona Dissódica 1g Pó Liofilizado Injetável IV (Profilaxia Cirúrgica)',
    'MEDICAMENTOS', 48.00,
    0, 6, 0, 0, NULL, NULL,
    'Cláusula 6.1 do Contrato Operadora-Prestador (Tabela TUSS 20 - Medicamentos Hospitalares)',
    'Antibioticoprofilaxia cirúrgica padrão de baixo valor compatível com cirurgia biliar.'
),
(
    '90289105', '20',
    'Ondansetrona Cloridrato 4mg/2ml Solução Injetável IV (Antiemético)',
    'MEDICAMENTOS', 19.50,
    0, 8, 0, 0, NULL, NULL,
    'Cláusula 6.2 do Contrato Operadora-Prestador (Tabela TUSS 20 - Medicamentos Hospitalares)',
    'Medicação antiemética pós-operatória de baixo valor compatível com internação cirúrgica.'
);
