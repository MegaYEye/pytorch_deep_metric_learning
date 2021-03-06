# coding=utf-8
from __future__ import absolute_import, print_function
import argparse
import os
import sys
import models
import time
import losses
import torch.utils.data
import torch.optim as optim
from torch.backends import cudnn
from torch.autograd import Variable
from tensorboardX import SummaryWriter
import torchvision.transforms as transforms
from utils import RandomIdentitySampler, mkdir_if_missing, logging
import DataSet
cudnn.benchmark = True

parser = argparse.ArgumentParser(description='PyTorch Training')
parser.add_argument('-data', default='cub', required=True,
                    help='data_name')
parser.add_argument('-loss', default='gaussian', required=True,
                    help='path to dataset')
parser.add_argument('-net', default='resnet_50',
                    help='network used')
parser.add_argument('-r', default=None,
                    help='the path of the pre-trained model')
parser.add_argument('-start', default=0, type=int,
                    help='resume epoch')

parser.add_argument('-log_dir', default=None,
                    help='where the trained models save')

parser.add_argument('-BatchSize', '-b', default=64, type=int, metavar='N',
                    help='mini-batch size (1 = pure stochastic) Default: 256')
parser.add_argument('-num_instances', default=16, type=int, metavar='n',
                    help='the number of samples from one class in mini-batch')
parser.add_argument('-dim', default=512, type=int, metavar='n',
                    help='the dimension of embedding space')

parser.add_argument('-epochs', '-epochs', default=100, type=int, metavar='N',
                    help='epochs for training process')
parser.add_argument('-step', '-s', default=1000, type=int, metavar='N',
                    help='number of epochs to adjust learning rate')
parser.add_argument('-save_step', default=10, type=int, metavar='N',
                    help='number of epochs to save model')
parser.add_argument('--print-freq', '-p', default=5, type=int,
                    metavar='N', help='print frequency (default: 10)')
# optimizer
parser.add_argument('-lr', type=float, default=1e-2,
                    help="learning rate of new parameters, for pretrained "
                         "parameters it is 10 times smaller than this")
parser.add_argument('--nThreads', '-j', default=4, type=int, metavar='N',
                    help='number of data loading threads (default: 2)')
parser.add_argument('--momentum', type=float, default=0.9)
parser.add_argument('--weight-decay', type=float, default=5e-5)

def accuracy(output, target, topk=(1,)):
    """Computes the precision@k for the specified values of k"""
    maxk = max(topk)
    batch_size = target.size(0)

    _, pred = output.topk(maxk, 1, True, True)
    pred = pred.t()
    temp = target.view(1, -1).expand_as(pred)
    temp = temp.cuda()
    correct = pred.eq(temp)

    res = []
    for k in topk:
        correct_k = correct[:k].view(-1).float().sum(0, keepdim=True)
        res.append(correct_k.mul_(100.0 / batch_size))
    return res

def data_info(data_name):
    if data_name == 'cub':
        root_dir = '/home/zhengxiawu/data/CUB_200_2011'
        train_folder = os.path.join(root_dir,'train_images')
        test_folder = os.path.join(root_dir,'test_images')
        num_class = 100
        return train_folder,test_folder,num_class

class AverageMeter(object):
    """Computes and stores the average and current value"""
    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count

args = parser.parse_args()

if args.log_dir is None:
    log_dir = os.path.join('checkpoints', args.loss)
else:
    log_dir = os.path.join('checkpoints', args.log_dir)
mkdir_if_missing(log_dir)
# write log
sys.stdout = logging.Logger(os.path.join(log_dir, 'log.txt'))
train_folder,test_folder,num_class = data_info(args.data)
#  display information of current training
print('train on dataset %s' % args.data)
print('batchsize is: %d' % args.BatchSize)
print('num_instance is %d' % args.num_instances)
print('dimension of the embedding space is %d' % args.dim)
print('log dir is: %s' % args.log_dir)

#  load fine-tuned models
if args.r is not None:
    model = torch.load(args.r)
else:
    model = models.create(args.net, Embed_dim=args.dim,
                          num_class = num_class,
                          pretrain = True)
#visualize the network

model = model.cuda()

criterion = losses.create(args.loss).cuda()

param_groups = model.parameters()
learn_rate = args.lr
# optimizer = optim.Adam(param_groups, lr=learn_rate,
#                        weight_decay=args.weight_decay)
optimizer = optim.SGD(param_groups, lr=learn_rate,
                      momentum=0.9, weight_decay=0.00005)

#get train_loader
if 'mxnet' in args.net:
    normalize = transforms.Normalize(mean=[123,117,104],
                                     std=[1,1,1])
else:
    normalize = transforms.Normalize(mean=[0.485, 0.456, 0.406],
                                         std=[0.229, 0.224, 0.225])
data = DataSet.create(args.data, root=None, test=False)
train_loader = torch.utils.data.DataLoader(
    data.train, batch_size=args.BatchSize,
    sampler=RandomIdentitySampler(data.train, num_instances=args.num_instances),
    drop_last=False, num_workers=args.nThreads)


def adjust_learning_rate(opt_, epoch_, num_epochs):
    """Sets the learning rate to the initial LR decayed by 1000 at last epochs"""
    if epoch_ > (num_epochs - args.step):
        lr = args.lr * \
             (0.01 ** ((epoch_ + args.step - num_epochs) / float(args.step)))
        for param_group in opt_.param_groups:
            param_group['lr'] = lr

#before we need prepare something...

batch_time = AverageMeter()
data_time = AverageMeter()
losses = AverageMeter()
top1 = AverageMeter()
top5 = AverageMeter()

end = time.time()
model.train()
for epoch in range(args.start, args.epochs):
    adjust_learning_rate(optimizer, epoch, args.epochs)
    running_loss = 0.0
    for i, data in enumerate(train_loader, 0):
        # get the inputs
        inputs, labels = data
        # if 'mxnet' in args.net:
        #     inputs = inputs * 255
        # normalize(inputs)
        # break
        # wrap them in Variable
        # inputs_var = Variable(inputs.cuda())
        # labels_var = Variable(labels).cuda()

        inputs_var = torch.autograd.Variable(inputs).cuda()
        labels_var = torch.autograd.Variable(labels).cuda()
        # zero the parameter gradients
        optimizer.zero_grad()

        # forward + backward + optimize
        embed_feat = model(inputs_var,scda=False,pool_type = 'max_avg',
                           is_train = True,scale = 128)
        # loss = criterion(embed_feat, labels)
        if args.loss == 'softmax':
            loss = criterion(embed_feat, labels_var)
            prec1, prec5 = accuracy(embed_feat.data, labels, topk=(1, 5))
            losses.update(loss.data[0], inputs.size(0))
            top1.update(prec1[0], inputs.size(0))
            top5.update(prec5[0], inputs.size(0))
        else:
            loss, inter_, dist_ap, dist_an = criterion(embed_feat, labels)
            print('[epoch %05d]\t loss: %.7f \t prec: %.3f \t pos-dist: %.3f \tneg-dist: %.3f'
                  % (epoch + 1, running_loss, inter_, dist_ap, dist_an))

        loss.backward()
        optimizer.step()
        if i % args.print_freq == 0:
            print('Epoch: [{0}][{1}/{2}]\t'
                  'Time {batch_time.val:.3f} ({batch_time.avg:.3f})\t'
                  'Data {data_time.val:.3f} ({data_time.avg:.3f})\t'
                  'Loss {loss.val:.4f} ({loss.avg:.4f})\t'
                  'Prec@1 {top1.val:.3f} ({top1.avg:.3f})\t'
                  'Prec@5 {top5.val:.3f} ({top5.avg:.3f})'.format(
                epoch, i, len(train_loader), batch_time=batch_time,
                data_time=data_time, loss=losses, top1=top1, top5=top5))
    # print(epoch)

    if epoch % args.save_step == 0:
        torch.save(model, os.path.join(log_dir, '%d_model.pth' % epoch))

torch.save(model, os.path.join(log_dir, '%d_model.pth' % epoch))

print('Finished Training')
